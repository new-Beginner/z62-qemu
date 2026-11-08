"""Read original Z62 wait-object STR before/after, without debugger state writes."""
import argparse
from datetime import datetime, timezone
import json
import math
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
from observe_boot_wait import BootRemote, BootSession, build_command, sample, FALSE_FIELDS
from observe_task_context import ticks, SOURCES as CONTEXT_SOURCES
from wait_store_contract import TOOL, collect, bounded_ram, check_event, summarize

SOURCES = tuple(sorted(set(CONTEXT_SOURCES + (
    'fenestra/z62/observe_wait_store.py', 'fenestra/z62/wait_store_contract.py',
    'fenestra/z62/task_wait_provenance.py', 'fenestra/z62/verify_task_context.py',
    'fenestra/z62/verify_boot_wait.py'))))


def run(output, max_stops=256, guest_seconds=3, wall_seconds=120):
    output = output.resolve()
    require(output.is_relative_to(ROOT / 'analysis') and not output.exists(), 'Use new analysis output')
    require(type(max_stops) is int and 32 <= max_stops <= 512 and math.isfinite(guest_seconds) and
            1 <= guest_seconds <= 6 and 30 <= wall_seconds <= 180, 'Invalid bounded observation limits')
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
        events=[], pauses=[], owned_shutdown='QMP quit; NOT camera normal shutdown',
        wait_registration_completed=False, task_identity_verified=False, hardware_root_cause_identified=False,
        **{n: False for n in FALSE_FIELDS})
    output.parent.mkdir(parents=True, exist_ok=True)
    log_path = output.with_suffix('.qemu.log')
    require(not log_path.exists(), 'Log already exists')
    process = remote = session = qmp_sock = qmp_stream = None
    error = row = None
    points = sorted(p['checkpoint'] for p in contract['roles'].values())
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
            session = BootSession(); session.qmp = qmp_stream
            json.loads(qmp_stream.readline())
            session.query('qmp_capabilities')
            remote = BootRemote(ports[0])
            record['model_tree'] = session.query('human-monitor-command', {'command-line': 'info qtree'})
            for pc in points:
                remote.breakpoint(pc)
            start = time.monotonic()
            record['trace_stop_reason'] = 'sample-bound'
            for index in range(max_stops):
                remaining = wall_seconds - (time.monotonic() - start)
                if remaining <= 0:
                    record['trace_stop_reason'] = 'wall-bound'
                    break
                remote.sock.settimeout(min(15, remaining))
                try:
                    stop = remote.command('c')
                except socket.timeout:
                    remote.sock.settimeout(15); stop = remote.interrupt()
                    record['pauses'].append(dict(phase='trace', stop=stop, ticks=ticks(remote)))
                    require(stop.startswith('T02'), 'Unexpected trace pause')
                    record['trace_stop_reason'] = 'quiet-switch-to-guest-deadline'
                    break
                remote.sock.settimeout(15)
                require(stop.startswith('T05'), 'Unexpected original STR breakpoint')
                previous = remote.command('qC'); tid = stopped_thread(stop, previous)
                remote.select_thread(int(tid, 16))
                packet = remote.regs(); regs = {n: remote.get(packet, n) for n in REGISTERS}
                head = remote.read(BASE, 0x6C)
                roles = [r for r, image in images.items() if head == image[:0x6C]]
                require(len(roles) == 1, 'Missing original role identity')
                role = roles[0]; p = contract['roles'][role]; pc = regs['pc']
                require(pc == p['checkpoint'], 'Wrong original wait STR checkpoint')
                for address, size in ((regs['r1'],256),(regs['r4'],24),(regs['sp'],80)):
                    require(bounded_ram(p['context'], address, size), 'Unbounded wait object/control block/stack')
                row = dict(sequence=index, role=role, thread=tid, stop=stop, previous_selected_thread=previous,
                    registers=regs, image_head=head.hex(),
                    system={n: remote.read_register(n) for n in SYSTEM},
                    current=list(struct.unpack('<2I', remote.read(p['context']['current'], 8))),
                    object_before=remote.read(regs['r4'],24).hex(), tcb_before=remote.read(regs['r1'],256).hex(),
                    call_stack_address=regs['sp']+16, call_stack=remote.read(regs['sp']+16,64).hex(),
                    rom_window=dict(address=pc-16, bytes=remote.read(pc-16,32).hex()), model_ticks=ticks(remote))
                require(row['rom_window']['bytes'] == images[role][pc-BASE-16:pc-BASE+16].hex(),
                        'Runtime original STR ROM changed')
                remote.select_thread(int(tid,16))
                row['step_reply'] = advance_isolated(remote, pc, tid, True)
                remote.select_thread(int(tid,16))
                packet = remote.regs(); row['after_registers'] = {n: remote.get(packet,n) for n in REGISTERS}
                row['object_after'] = remote.read(regs['r4'],24).hex()
                row['tcb_after'] = remote.read(regs['r1'],256).hex()
                row['analysis'] = check_event(row,p)
                record['events'].append(row)
                if len(record['events']) % 128 == 0:
                    print('original STR samples',len(record['events']),flush=True)
            for pc in points:
                remote.breakpoint(pc,False)
            record['trace_end_ticks'] = ticks(remote)
            while ticks(remote) < guest_seconds * 48000000:
                remaining = wall_seconds - (time.monotonic()-start)
                if remaining <= 0:
                    break
                remote.sock.settimeout(min(15,remaining))
                try:
                    stop = remote.command('c')
                except socket.timeout:
                    remote.sock.settimeout(15); stop = remote.interrupt()
                remote.sock.settimeout(15)
                require(stop.startswith('T02'),'Unexpected untraced stop')
                record['pauses'].append(dict(phase='untraced',stop=stop,ticks=ticks(remote)))
            record['final_ticks'] = ticks(remote)
            record['guest_target_reached'] = record['final_ticks'] >= guest_seconds * 48000000
            record['final_cpus'] = sample(remote,images)
            record['final_status'] = session.query('query-status')
            record['summary'] = summarize(record['events'],contract)
            record['wall_seconds'] = time.monotonic()-start
            record['quit_receipt'] = quit_owned(session,process)
            record['completed'] = True
        except Exception as exc:
            error = exc; record['failure'] = type(exc).__name__ + ': ' + str(exc)
            if row is not None:
                record['failure_event'] = row
        finally:
            if process is not None and process.poll() is None and session is not None:
                try:
                    record['quit_receipt'] = quit_owned(session,process)
                except Exception as exc:
                    record['quit_failure'] = type(exc).__name__ + ': ' + str(exc)
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait(timeout=10)
            record['exit_code'] = None if process is None else process.returncode
            record['owned_process_closed'] = process is not None and process.poll() is not None
            record['rsp_commands'] = getattr(remote,'audit',[])
            record['rsp_controls'] = getattr(remote,'controls',[])
            record['qmp_commands'] = getattr(session,'audit',[])
            record['close_notes'] = close_handles([getattr(remote,'sock',None),qmp_stream,qmp_sock])
            record['log_sha256'] = sha(log_path.read_bytes()) if log_path.exists() else None
            json.dump(record,evidence,indent=2); evidence.write('\n')
    if error is not None:
        raise error
    require(record['exit_code'] == 0 and record['owned_process_closed'],'Owned process did not close')
    print('summary events', {r:s['events'] for r,s in record['summary'].items()},flush=True)
    return record


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--max-stops',type=int,default=256)
    parser.add_argument('--guest-seconds',type=float,default=3)
    parser.add_argument('--wall-seconds',type=int,default=120)
    args = parser.parse_args()
    run(args.output,args.max_stops,args.guest_seconds,args.wall_seconds)
