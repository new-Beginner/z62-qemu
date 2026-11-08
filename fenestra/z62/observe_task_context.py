"""Bounded stock context-save trace on pinned r69. No task ABI/boot/flash claim."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import time

from startup_contract import ROOT, BASE, require, sha, read_inputs
from pool_calls import REGISTERS, SYSTEM
from observe_startup import QEMU_REL, QEMU_SHA, free_port, connect, stopped_thread
from observe_pool import advance_isolated, quit_owned, close_handles
from observe_boot_wait import BootRemote, BootSession, build_command, sample as cpu_sample, FALSE_FIELDS
from task_context import TOOL, collect, bounded_ram, check_event, summarize

SOURCES = ('fenestra/z62/observe_task_context.py', 'fenestra/z62/task_context.py',
           'fenestra/z62/observe_boot_wait.py', 'fenestra/z62/observe_pool.py',
           'fenestra/z62/observe_startup.py', 'fenestra/z62/startup_contract.py',
           'fenestra/z62/memory_contract.py', 'fenestra/z62/pool_calls.py',
           'third_party/z62-qemu/analyze/qemu_display.py',
           'tools/probe_reference_devices.py', 'tools/probe_z62_functional_raw.py')


def ticks(remote):
    remote.select_thread(1)
    return int.from_bytes(remote.read(0x04266008, 8), 'little')


def saved_snapshot(remote, p, pointer):
    require(bounded_ram(p, pointer, 256), 'Control block outside original heap')
    block = remote.read(pointer, 256)
    sp = struct.unpack_from('<I', block, 0xBC)[0]
    result = dict(pointer=pointer, tcb=block.hex(), frame_address=sp)
    if bounded_ram(p, sp, 96):
        result['frame'] = remote.read(sp, 96).hex()
    else:
        result['unresolved'] = 'Saved pointer is not a bounded original-heap frame; no lifetime inference'
    return result


def run(output, max_stops=600, guest_seconds=5, wall_seconds=180):
    output = output.resolve()
    require(output.is_relative_to(ROOT / 'analysis') and not output.exists(), 'Use new analysis output')
    require(16 <= max_stops <= 1000 and 1 <= guest_seconds <= 10 and 30 <= wall_seconds <= 180,
            'Invalid bounded task observation limits')
    root = Path('Q:/')
    require(root.is_dir() and root.samefile(ROOT), 'Verified Q: workspace alias required')
    require(sha((root / QEMU_REL).read_bytes()) == QEMU_SHA, 'Pinned QEMU changed')
    contract, images = collect(), read_inputs()
    ports = free_port(), free_port()
    command = build_command(root, 'minimal', *ports)
    record = dict(schema=1, tool=TOOL, created_at=datetime.now(timezone.utc).isoformat(),
        completed=False, command=command, qemu_sha256=QEMU_SHA, contract=contract,
        sources={n: sha((ROOT / n).read_bytes()) for n in SOURCES},
        firmware_loaded=True, controller_loaded=False, controller_link_enabled=False,
        reset_pc_initialized_by_qemu_loader=True, breakpoint_timing_perturbed=True,
        max_stops=max_stops, guest_target_seconds=guest_seconds, wall_limit_seconds=wall_seconds,
        events=[], steps=[], pauses=[], final_saved={},
        owned_shutdown='QMP quit; NOT camera normal shutdown',
        **{n: False for n in FALSE_FIELDS})
    output.parent.mkdir(parents=True, exist_ok=True)
    log_path = output.with_suffix('.qemu.log')
    require(not log_path.exists(), 'Log already exists')
    process = remote = session = qmp_sock = qmp_stream = None
    error = row = None
    points = {p['checkpoint'] for p in contract['roles'].values()}
    with output.open('x', encoding='utf-8') as evidence:
        try:
            env = dict(os.environ, TEMP=os.environ['PI_SCRATCH_DIR'], TMP=os.environ['PI_SCRATCH_DIR'],
                       TMPDIR=os.environ['PI_SCRATCH_DIR'], PYTHONDONTWRITEBYTECODE='1')
            with log_path.open('xb') as log:
                process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=log, env=env)
            record['owned_pid'] = process.pid
            qmp_sock = connect(ports[1], process)
            qmp_sock.settimeout(15)
            qmp_stream = qmp_sock.makefile('rwb')
            session = BootSession()
            session.qmp = qmp_stream
            json.loads(qmp_stream.readline())
            session.query('qmp_capabilities')
            remote = BootRemote(ports[0])
            record['model_tree'] = session.query('human-monitor-command', {'command-line': 'info qtree'})
            for pc in sorted(points):
                remote.breakpoint(pc)
            start = time.monotonic()
            record['trace_stop_reason'] = 'context-sample-bound'
            for index in range(max_stops):
                remaining = wall_seconds - (time.monotonic() - start)
                if remaining <= 0:
                    record['trace_stop_reason'] = 'wall-bound'
                    break
                remote.sock.settimeout(min(15, remaining))
                try:
                    stop = remote.command('c')
                except socket.timeout:
                    remote.sock.settimeout(15)
                    stop = remote.interrupt()
                    record['pauses'].append(dict(phase='trace', stop=stop, ticks=ticks(remote)))
                    require(stop.startswith(('T02', 'S02')), 'Unexpected quiet-window stop')
                    record['trace_stop_reason'] = 'quiet-window-switch-to-untraced-guest-deadline'
                    break
                remote.sock.settimeout(15)
                require(stop.startswith(('T05', 'S05')), 'Unexpected context breakpoint: ' + stop)
                current = remote.command('qC')
                tid = stopped_thread(stop, current)
                remote.select_thread(int(tid, 16))
                data = remote.regs()
                regs = {n: remote.get(data, n) for n in REGISTERS}
                head = remote.read(BASE, 0x6C)
                roles = [r for r, d in images.items() if head == d[:0x6C]]
                require(len(roles) == 1, 'Original engine identity missing')
                role = roles[0]
                p = contract['roles'][role]
                require(regs['pc'] == p['checkpoint'], 'Wrong context-save checkpoint')
                require(bounded_ram(p, regs['r8'], 256) and bounded_ram(p, regs['sp'], 96),
                        'Context pointers outside original heap')
                snapshot = saved_snapshot(remote, p, regs['r8'])
                row = dict(sequence=index, role=role, thread=tid, stop=stop,
                    previous_selected_thread=current, registers=regs,
                    system_registers={n: remote.read_register(n) for n in SYSTEM},
                    current=list(struct.unpack('<2I', remote.read(p['current'], 8))),
                    tcb=snapshot['tcb'], frame_address=snapshot['frame_address'], frame=snapshot['frame'],
                    image_head=head.hex(), model_ticks=ticks(remote))
                # ticks() selects CPU01; restore the actual stopping CPU for its ROM view/step.
                remote.select_thread(int(tid, 16))
                pc = regs['pc']
                raw = remote.read(pc - 16, 32)
                require(raw == images[role][pc - BASE - 16:pc - BASE + 16], 'Original context code changed')
                row['rom_window'] = dict(address=pc - 16, bytes=raw.hex())
                row['analysis'] = check_event(row, p)
                record['events'].append(row)
                reply = advance_isolated(remote, pc, tid, True)
                remote.select_thread(int(tid, 16))
                after = remote.regs()
                step_regs = {n: remote.get(after, n) for n in REGISTERS}
                require(step_regs['pc'] == pc + 4 and step_regs['sp'] == p['system_stack'],
                        'Original LDR did not select the system-stack base')
                record['steps'].append(dict(address=pc, thread=tid, reply=reply, registers=step_regs))
                if len(record['events']) % 100 == 0:
                    print('context events', len(record['events']), flush=True)
            for pc in sorted(points):
                remote.breakpoint(pc, False)
            record['trace_end_ticks'] = ticks(remote)
            while ticks(remote) < guest_seconds * 48000000:
                remaining = wall_seconds - (time.monotonic() - start)
                if remaining <= 0:
                    break
                remote.sock.settimeout(min(15, remaining))
                try:
                    stop = remote.command('c')
                except socket.timeout:
                    remote.sock.settimeout(15)
                    stop = remote.interrupt()
                remote.sock.settimeout(15)
                require(stop.startswith(('T02', 'S02')), 'Unexpected untraced stop')
                record['pauses'].append(dict(phase='untraced', stop=stop, ticks=ticks(remote)))
            record['final_ticks'] = ticks(remote)
            record['guest_target_reached'] = record['final_ticks'] >= guest_seconds * 48000000
            record['final_cpus'] = cpu_sample(remote, images)
            record['final_status'] = session.query('query-status')
            for role, p in contract['roles'].items():
                remote.select_thread(1 if role == 'master' else 3)
                addresses = sorted({r['registers']['r8'] for r in record['events'] if r['role'] == role})
                require(len(addresses) <= 512, 'Too many observed control blocks')
                record['final_saved'][role] = [saved_snapshot(remote, p, a) for a in addresses]
            record['summary'] = summarize(record['events'], contract)
            record['wall_seconds'] = time.monotonic() - start
            record['quit_receipt'] = quit_owned(session, process)
            record['completed'] = True
        except Exception as exc:
            error = exc
            record['failure'] = type(exc).__name__ + ': ' + str(exc)
            if row is not None:
                record['failure_event'] = row
        finally:
            if process is not None and process.poll() is None and session is not None:
                try:
                    record['quit_receipt'] = quit_owned(session, process)
                except Exception as exc:
                    record['quit_failure'] = type(exc).__name__ + ': ' + str(exc)
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
            record['exit_code'] = None if process is None else process.returncode
            record['owned_process_closed'] = process is not None and process.poll() is not None
            record['rsp_commands'] = getattr(remote, 'audit', [])
            record['rsp_controls'] = getattr(remote, 'controls', [])
            record['qmp_commands'] = getattr(session, 'audit', [])
            record['close_notes'] = close_handles([getattr(remote, 'sock', None), qmp_stream, qmp_sock])
            record['log_sha256'] = sha(log_path.read_bytes()) if log_path.exists() else None
            json.dump(record, evidence, indent=2)
            evidence.write('\n')
    if error is not None:
        raise error
    require(record['exit_code'] == 0 and record['owned_process_closed'], 'Owned process did not close cleanly')
    print(json.dumps(record['summary'], indent=2), flush=True)
    return record


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--max-stops', type=int, default=600)
    parser.add_argument('--guest-seconds', type=float, default=5)
    parser.add_argument('--wall-seconds', type=int, default=180)
    args = parser.parse_args()
    run(args.output, args.max_stops, args.guest_seconds, args.wall_seconds)
