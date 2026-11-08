"""Read-only bounded natural stock byte-heap observation on pinned self-developed r69."""
import argparse
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import time

from heap_calls import collect, descriptor, valid_header, analyze_events, summarize, FALSE_FIELDS, TOOL
from pool_calls import REGISTERS, SYSTEM, Ledger, check_event as check_cpu
from startup_contract import ROOT, BASE, read_inputs, require, sha
from observe_startup import QEMU_REL, QEMU_SHA, Session, free_port, connect, stopped_thread
from observe_pool import ReadOnlyRemote, advance_isolated, quit_owned, close_handles

SOURCES = ('fenestra/z62/observe_heap.py', 'fenestra/z62/heap_calls.py', 'fenestra/z62/heap_contract.py',
           'fenestra/z62/observe_pool.py', 'fenestra/z62/pool_calls.py', 'fenestra/z62/observe_startup.py',
           'fenestra/z62/startup_contract.py', 'fenestra/z62/memory_contract.py',
           'third_party/z62-qemu/analyze/qemu_display.py', 'tools/probe_reference_devices.py',
           'tools/probe_z62_functional_raw.py')


def snapshot(remote, p, desc, pointer=None, seeds=()):
    require(desc in {v['base'] for v in p['descriptors']}, 'Descriptor outside original groups')
    addresses = {a for a in seeds if valid_header(p, a)}
    if pointer:
        require(valid_header(p, pointer - 8), 'User pointer outside bounded heap')
        addresses.add(pointer - 8)
    nodes = {}
    # Two bounded links, not an unbounded chain traversal or a claim of physical DRAM capacity.
    for depth in range(3):
        require(len(addresses) <= 24, 'Heap snapshot bound exceeded')
        for address in sorted(addresses - nodes.keys()):
            nodes[address] = list(struct.unpack('<2I', remote.read(address, 8)))
        if depth < 2:
            for words in list(nodes.values()):
                addresses.update(a for a in (words[0], words[1] & ~7) if valid_header(p, a))
    return dict(descriptor=desc, descriptor_words=list(struct.unpack('<7I', remote.read(desc, 28))),
                control=list(struct.unpack('<2I', remote.read(p['heap_control'], 8))),
                pool_state=list(struct.unpack('<4I', remote.read(p['pool_state'], 16))),
                headers=[dict(address=a, words=w) for a, w in sorted(nodes.items())])


def run(output, max_stops=2000, wall_seconds=180):
    output = output.resolve()
    require(output.is_relative_to(ROOT / 'analysis') and not output.exists(), 'Use new analysis output')
    require(16 <= max_stops <= 6000 and 10 <= wall_seconds <= 300, 'Invalid bounded observation limits')
    root = Path('Q:/')
    require(root.is_dir() and root.samefile(ROOT), 'Verified Q: workspace alias required')
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
    record = dict(schema=1, tool=TOOL, completed=False, command=command, qemu_sha256=QEMU_SHA,
                  sources={n: sha((ROOT / n).read_bytes()) for n in SOURCES}, contract=contract,
                  **{n: False for n in FALSE_FIELDS}, firmware_loaded=True,
                  reset_pc_initialized_by_qemu_loader=True, breakpoint_timing_perturbed=True,
                  max_stops=max_stops, drain_limit=64, wall_limit_seconds=wall_seconds,
                  events=[], ignored=[], steps=[], page_tables={},
                  owned_shutdown='QMP quit; NOT camera normal shutdown')
    entries = {role: {p[k]: k for k in ('allocate', 'release')} for role, p in contract['roles'].items()}
    permanent = {pc for points in entries.values() for pc in points}
    active, ledger = set(permanent), Ledger()
    output.parent.mkdir(parents=True, exist_ok=True)
    log_path = output.with_suffix('.qemu.log')
    require(not log_path.exists(), 'Log already exists')
    process = remote = session = qmp_sock = qmp_stream = None
    error = row = None
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
            record['stop_reason'] = 'hard-stop-bound'
            for stop_number in range(max_stops + 64):
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
                row = dict(sequence=len(record['events']), role=role, thread=tid, registers=registers,
                           stop=stop, previous_selected_thread=current, stop_number=stop_number,
                           wall_seconds=round(time.monotonic() - start, 3))
                found = ledger.match(row)
                if pc in entries[role]:
                    require(found is None, 'Entry/return breakpoint alias')
                    row['kind'] = entries[role][pc]
                    desc = descriptor(p, row)
                    pointer = registers['r0'] if row['kind'] == 'release' else None
                    row['heap'] = snapshot(remote, p, desc, pointer)
                    ledger.enter(row)
                elif found is not None:
                    row['kind'] = 'return'
                    entry = ledger.pending[found]['entry']
                    desc = descriptor(p, entry)
                    pointer = registers['r0'] if entry['kind'] == 'allocate' else entry['registers']['r0']
                    seeds = [n['address'] for n in entry['heap']['headers']]
                    row['heap'] = snapshot(remote, p, desc, pointer, seeds)
                    ledger.returned(found, row)
                else:
                    record['ignored'].append(dict(role=role, thread=tid, registers=registers, stop=stop))
                    require(pc in active, 'Unexpected unregistered breakpoint')
                    advance_isolated(remote, pc, tid, True)
                    continue
                row['system_registers'] = {n: remote.read_register(n) for n in SYSTEM}
                check_cpu(row, contract)
                require(BASE + 8 <= pc <= BASE + len(images[role]) - 16, 'Call site outside original ROM')
                window = remote.read(pc - 8, 24)
                require(window == images[role][pc - BASE - 8:pc - BASE + 16], 'Original call-site bytes differ')
                row['rom_window'] = dict(address=pc - 8, bytes=window.hex())
                if role not in record['page_tables']:
                    table = remote.read(p['copied_table'], 0x4000)
                    require(table == images[role][0x10000:0x14000], 'Original RAM table differs')
                    record['page_tables'][role] = sha(table)
                record['events'].append(row)
                desired = permanent | ledger.return_addresses()
                for address in sorted(desired - active):
                    remote.breakpoint(address)
                step = dict(address=pc, requested_thread=tid, keep=pc in desired)
                record['steps'].append(step)
                step['reply'] = advance_isolated(remote, pc, tid, pc in desired)
                if step['reply'] is not None:
                    actual = stopped_thread(step['reply'], remote.command('qC'))
                    remote.select_thread(int(actual, 16))
                    after = remote.regs()
                    step.update(actual_thread=actual, registers={n: remote.get(after, n) for n in REGISTERS})
                    require(actual == tid, 'Single-step stopped another CPU')
                    if pc in permanent:
                        require(step['registers']['pc'] == pc + 4, 'Entry did not advance original ARM instruction')
                for address in sorted(active - desired - {pc}):
                    remote.breakpoint(address, False)
                active = desired
                if len(record['events']) % 100 == 0:
                    print('heap events', len(record['events']), 'pending', len(ledger.pending), flush=True)
                if not ledger.pending:
                    if stop_number + 1 >= max_stops:
                        record['stop_reason'] = 'soft-stop-bound-drained'
                        break
                    if len(record['events']) % 50 == 0:
                        _, results = analyze_events(record['events'], contract)
                        summary = summarize(ledger.calls, results)
                        if all(s['allocations'] >= 64 and s['release_metadata'] >= 8 and
                               s['exact_pointer_reuses'] >= 2 for s in summary.values()):
                            record['stop_reason'] = 'bounded-sample-target'
                            break
            record['wall_seconds'] = round(time.monotonic() - start, 3)
            replay, results = analyze_events(record['events'], contract)
            require(replay.calls == ledger.calls, 'Live/replayed heap ledger differs')
            record.update(calls=ledger.calls, results=results, pending_ids=sorted(ledger.pending),
                          summary=summarize(ledger.calls, results))
            record['quit_receipt'] = quit_owned(session, process)
            record['completed'] = True
        except Exception as exc:
            error = exc
            record['failure'] = dict(type=type(exc).__name__, message=str(exc))
            record['calls'], record['pending_ids'] = ledger.calls, sorted(ledger.pending)
            if row is not None:
                record['failure_event'] = row
            if session is not None and process is not None and process.poll() is None:
                try:
                    record['quit_receipt'] = quit_owned(session, process)
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
    parser.add_argument('--max-stops', type=int, default=2000)
    parser.add_argument('--wall-seconds', type=int, default=180)
    args = parser.parse_args()
    run(args.output, args.max_stops, args.wall_seconds)
