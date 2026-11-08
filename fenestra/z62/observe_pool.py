"""Observe natural stock Z62 pool calls on pinned local QEMU, without injection."""
import argparse
import json
import os
from pathlib import Path
import re
import socket
import struct
import subprocess
import time

from pool_calls import (REGISTERS, SYSTEM, FALSE_FIELDS, Ledger, collect, header_index,
                        sample_indices, extent, analyze_events, summarize, check_event)
from startup_contract import ROOT, BASE, read_inputs, require, sha
from observe_startup import (QEMU_REL, QEMU_SHA, Remote, Session, free_port, connect,
                             stopped_thread)


class ReadOnlyRemote(Remote):
    def command(self, payload):
        allowed = (payload in ('g', 'c', 'qC', 'qfThreadInfo') or
                   payload.startswith(('qSupported:', 'qXfer:features:read:')) or
                   re.fullmatch(r'(?:Hg[0-9a-f]+|p[0-9a-f]+|vCont;s:[0-9a-f]+|'
                                r'm[0-9a-f]+,[0-9a-f]+|[Zz]1,[0-9a-f]+,2)', payload))
        require(bool(allowed), 'Forbidden debugger command: ' + payload)
        if not hasattr(self, 'audit'):
            self.audit = []
        self.audit.append(payload)
        return super().command(payload)


def quit_owned(session, process):
    receipt = dict(acknowledged=False)
    try:
        session.query('quit')
        receipt['acknowledged'] = True
    except (OSError, ValueError) as exc:
        receipt['transport_note'] = type(exc).__name__ + ': ' + str(exc)
    process.wait(timeout=15)
    require(process.returncode == 0, 'Owned QEMU exit was not zero')
    return receipt


def close_handles(handles):
    failures = []
    for handle in handles:
        if handle is not None:
            try:
                handle.close()
            except OSError as exc:
                failures.append(type(exc).__name__ + ': ' + str(exc))
    return failures


def advance_isolated(remote, address, thread, keep):
    """Traditional s resumes all CPUs in QEMU system mode. Use per-CPU vCont."""
    remote.breakpoint(address, False)
    if not keep:
        return None
    reply = remote.command('vCont;s:' + thread)
    require(reply.startswith(('T05', 'S05')), 'Unexpected isolated-step reply: ' + reply)
    require(stopped_thread(reply, remote.command('qC')) == thread, 'Isolated step changed CPU')
    remote.breakpoint(address)
    return reply


def snapshot(remote, p, pointer=None, blocks=None):
    g = p['geometry']
    return dict(state=list(struct.unpack('<4I', remote.read(p['pool_state'], 16))),
                headers=[dict(index=i, address=g['start'] + i * 8,
                              words=list(struct.unpack('<2I', remote.read(g['start'] + i * 8, 8))))
                         for i in sample_indices(g, pointer, blocks)])


def run(output, max_stops=240, wall_seconds=120):
    output = output.resolve()
    require(output.is_relative_to(ROOT / 'analysis') and not output.exists(), 'Use new analysis output')
    require(8 <= max_stops <= 1000 and 10 <= wall_seconds <= 300, 'Invalid bounded limits')
    root = Path('Q:/')
    require(root.is_dir() and root.samefile(ROOT), 'Verified Q: alias required')
    binary = root / QEMU_REL
    require(sha(binary.read_bytes()) == QEMU_SHA, 'Pinned QEMU changed')
    contract, images = collect(), read_inputs()
    qmp_port, gdb_port = free_port(), free_port()
    require(qmp_port != gdb_port, 'Port collision')
    machine = ('nikon-z62-dual-lab,'
               f'master-boot-image={root}/artifacts/z62-reference-1.70/master.bin,'
               f'slave-boot-image={root}/artifacts/z62-reference-1.70/slave.bin')
    command = [str(binary), '-M', machine, '-smp', '4,maxcpus=5', '-S', '-display', 'none',
               '-serial', 'none', '-monitor', 'none', '-nic', 'none',
               '-gdb', f'tcp:127.0.0.1:{gdb_port}', '-icount', 'shift=0,sleep=off',
               '-qmp', f'tcp:127.0.0.1:{qmp_port},server=on,wait=off']
    for cpu in range(4):
        command += ['-device', f'loader,addr={BASE:#x},cpu-num={cpu}']
    names = ('fenestra/z62/observe_pool.py', 'fenestra/z62/pool_calls.py',
             'fenestra/z62/observe_startup.py', 'third_party/z62-qemu/analyze/qemu_display.py',
             'tools/probe_reference_devices.py', 'tools/probe_z62_functional_raw.py')
    record = dict(schema=1, completed=False, command=command, qemu_sha256=QEMU_SHA,
                  sources={n: sha((ROOT / n).read_bytes()) for n in names}, contract=contract,
                  **{n: False for n in FALSE_FIELDS}, firmware_loaded=True,
                  reset_pc_initialized_by_qemu_loader=True, breakpoint_timing_perturbed=True,
                  max_stops=max_stops, wall_limit_seconds=wall_seconds, events=[], ignored=[], steps=[],
                  page_tables={}, owned_shutdown='QMP quit; NOT camera normal shutdown')
    entries = {role: {p['observed_api'][k]: k for k in ('allocate', 'release')}
               for role, p in contract['roles'].items()}
    permanent = {pc for points in entries.values() for pc in points}
    active, ledger = set(permanent), Ledger()
    output.parent.mkdir(parents=True, exist_ok=True)
    log_path = output.with_suffix('.qemu.log')
    require(not log_path.exists(), 'Log already exists')
    process = remote = session = qmp_sock = qmp_stream = None
    error = None
    with output.open('x', encoding='utf-8') as evidence:
        try:
            env = dict(os.environ, TEMP=os.environ['PI_SCRATCH_DIR'], TMP=os.environ['PI_SCRATCH_DIR'],
                       TMPDIR=os.environ['PI_SCRATCH_DIR'], PYTHONDONTWRITEBYTECODE='1')
            with log_path.open('xb') as log:
                process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=log, env=env)
            record['owned_pid'] = process.pid
            qmp_sock = connect(qmp_port, process)
            qmp_sock.settimeout(5)
            qmp_stream = qmp_sock.makefile('rwb')
            session = Session()
            session.qmp = qmp_stream
            json.loads(qmp_stream.readline())
            session.query('qmp_capabilities')
            remote = ReadOnlyRemote(gdb_port)
            record['gdb_threads'] = remote.command('qfThreadInfo')
            for address in sorted(active):
                remote.breakpoint(address)
            start = time.monotonic()
            record['stop_reason'] = 'max-stops'
            for stop_number in range(max_stops):
                remaining = wall_seconds - (time.monotonic() - start)
                if remaining <= 0:
                    record['stop_reason'] = 'wall-limit'
                    break
                remote.sock.settimeout(min(15, remaining))
                try:
                    stop = remote.command('c')
                except socket.timeout:
                    record['stop_reason'] = 'no-breakpoint-within-bounded-receive'
                    break
                remote.sock.settimeout(15)
                require(stop.startswith(('T05', 'S05')), 'Unexpected stop ' + stop)
                current = remote.command('qC')
                tid = stopped_thread(stop, current)
                remote.select_thread(int(tid, 16))
                regs = remote.regs()
                registers = {n: remote.get(regs, n) for n in REGISTERS}
                head = remote.read(BASE, 0x6C)
                roles = [r for r, d in images.items() if head == d[:0x6C]]
                require(len(roles) == 1, 'Stopped CPU image is not original')
                role = roles[0]
                p, pc = contract['roles'][role], registers['pc']
                row = dict(sequence=len(record['events']), role=role, thread=tid,
                           registers=registers, stop=stop, previous_selected_thread=current,
                           stop_number=stop_number, wall_seconds=round(time.monotonic() - start, 3))
                call_id = ledger.match(row)
                if pc in entries[role]:
                    require(call_id is None, 'Entry and return breakpoint alias')
                    row['kind'] = entries[role][pc]
                    er = registers
                    pointer = er['r0'] if row['kind'] == 'release' else None
                    row['pool'] = snapshot(remote, p, pointer)
                    n = extent(row['pool'], p['geometry'], pointer)
                    if n is not None:
                        row['pool'] = snapshot(remote, p, pointer, n)
                    ledger.enter(row)
                elif call_id is not None:
                    row['kind'] = 'return'
                    e = ledger.pending[call_id]['entry']
                    ptr = registers['r0'] if e['kind'] == 'allocate' else e['registers']['r0']
                    n = e['registers']['r0'] if e['kind'] == 'allocate' else extent(e['pool'], p['geometry'], ptr)
                    row['pool'] = snapshot(remote, p, ptr, n)
                    ledger.returned(call_id, row)
                else:
                    record['ignored'].append(dict(role=role, thread=tid, registers=registers,
                                                  stop=stop, stop_number=stop_number))
                    require(pc in active, 'Unexpected unregistered breakpoint')
                    advance_isolated(remote, pc, tid, True)
                    continue
                row['system_registers'] = {n: remote.read_register(n) for n in SYSTEM}
                check_event(row, contract)
                require(BASE + 8 <= pc <= BASE + len(images[role]) - 16, 'Call site outside original ROM')
                window = remote.read(pc - 8, 24)
                require(window == images[role][pc - BASE - 8:pc - BASE + 16], 'Original call-site bytes differ')
                row['rom_window'] = dict(address=pc - 8, bytes=window.hex())
                if role not in record['page_tables']:
                    table = remote.read(p['copied_table'], 0x4000)
                    require(table == images[role][0x10000:0x14000], 'Original RAM table differs')
                    record['page_tables'][role] = sha(table)
                record['events'].append(row)
                if row['kind'] != 'return' or len(record['events']) % 20 == 0:
                    print(role, row['kind'], hex(pc), 'r0=' + hex(registers['r0']), flush=True)
                desired = permanent | ledger.return_addresses()
                for address in sorted(desired - active):
                    remote.breakpoint(address)
                step = dict(address=pc, requested_thread=tid, keep=pc in desired)
                record['steps'].append(step)
                step['reply'] = advance_isolated(remote, pc, tid, pc in desired)
                if step['reply'] is not None:
                    actual_tid = stopped_thread(step['reply'], remote.command('qC'))
                    remote.select_thread(int(actual_tid, 16))
                    after = remote.regs()
                    step.update(actual_thread=actual_tid, registers={n: remote.get(after, n) for n in REGISTERS})
                    require(actual_tid == tid, 'Single-step stopped a different CPU')
                    if pc in permanent:
                        require(step['registers']['pc'] == pc + 4, 'Entry single-step did not advance one ARM instruction')
                for address in sorted(active - desired - {pc}):
                    remote.breakpoint(address, False)
                active = desired
                # Do not stop after allocations alone: try to observe natural release too.
                counts = {r: {k: sum(c['entry']['role'] == r and c['entry']['kind'] == k and
                                     c['return_event'] is not None for c in ledger.calls)
                              for k in ('allocate', 'release')} for r in images}
                if all(c['allocate'] >= 8 and c['release'] >= 2 for c in counts.values()) and not ledger.pending:
                    record['stop_reason'] = 'bounded-sample-target'
                    break
            record['wall_seconds'] = round(time.monotonic() - start, 3)
            replay, results = analyze_events(record['events'], contract)
            require(replay.calls == ledger.calls, 'Live/replayed ledger differs')
            record['calls'], record['results'] = ledger.calls, results
            record['pending_ids'] = sorted(ledger.pending)
            record['summary'] = summarize(results)
            record['quit_receipt'] = quit_owned(session, process)
            record['completed'] = True
        except Exception as exc:
            error = exc
            record['failure'] = dict(type=type(exc).__name__, message=str(exc))
            record['calls'] = ledger.calls
            record['pending_ids'] = sorted(ledger.pending)
            if session is not None and process is not None and process.poll() is None:
                try:
                    session.query('quit')
                    process.wait(timeout=10)
                except Exception as cleanup:
                    record['quit_failure'] = str(cleanup)
        finally:
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
            record['owned_process_closed'] = process is not None and process.poll() is not None
            record['exit_code'] = None if process is None else process.returncode
            record['rsp_commands'] = getattr(remote, 'audit', [])
            record['handle_close_failures'] = close_handles((getattr(remote, 'sock', None), qmp_stream, qmp_sock))
            if log_path.exists():
                record['log_sha256'] = sha(log_path.read_bytes())
            json.dump(record, evidence, indent=2)
            evidence.write('\n')
    if error is not None:
        raise error
    print(json.dumps({k: record[k] for k in ('completed', 'summary', 'pending_ids', 'stop_reason',
                                             'owned_process_closed', 'firmware_integrated', 'flash_safety_verified')}, indent=2))
    return record


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--max-stops', type=int, default=240)
    parser.add_argument('--wall-seconds', type=int, default=120)
    args = parser.parse_args()
    run(args.output, args.max_stops, args.wall_seconds)
