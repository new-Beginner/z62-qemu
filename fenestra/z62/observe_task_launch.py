"""Read-only r15 index3 call chains on the independently built r13 model."""
import argparse
import ctypes
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import time
from observe_task_create import (ROOT, BASE, REGISTERS, SYSTEM, free_port, connect, stopped_thread,
    BootSession, BootRemote, build_command, sample, ticks, selected_ticks, advance_isolated,
    quit_owned, close_handles, sha, require, read_inputs, FALSE_FIELDS as OLD_FALSE, SOURCES as OLD_SOURCES)
from observe_model_baseline import WORK, FALSE_FIELDS as MODEL_FALSE, SOURCES as MODEL_SOURCES
from task_launch_contract import (TOOL, LIMITATIONS, collect, bounded_ram, bounded_stack, check_input,
    check_prepared, classify, ingest, complete, ready, summarize)

FALSE_FIELDS = tuple(sorted(set(OLD_FALSE+MODEL_FALSE+LIMITATIONS)))
SOURCES = tuple(sorted(set(OLD_SOURCES+MODEL_SOURCES+(
    'fenestra/z62/task_entry_contract.py', 'fenestra/z62/verify_task_entry.py',
    'fenestra/z62/verify_task_context.py', 'fenestra/z62/verify_task_create.py',
    'fenestra/z62/task_launch_contract.py', 'fenestra/z62/observe_task_launch.py',
    'fenestra/z62/verify_task_launch.py'))))
OUTPUT = ROOT/'analysis/fenestra-z62-task-launch-r15'


def model_identity():
    manifest = WORK/'model-build.json'
    build = json.loads(manifest.read_text(encoding='utf-8'))
    require(build['binary_sha256'] == sha((WORK/'runtime/qemu-system-arm.exe').read_bytes()), 'New EXE differs')
    require(build['prepared_sha256'] == sha((WORK/'prepared.json').read_bytes()), 'Prepared identity differs')
    for name, expected in build['runtime_dll_sha256'].items():
        require(sha((WORK/'runtime'/name).read_bytes()) == expected, 'New runtime DLL differs: '+name)
    return dict(qemu_sha256=build['binary_sha256'], build_manifest_sha256=sha(manifest.read_bytes()))


def command(ports):
    result = build_command(Path('Q:/'), 'minimal', *ports)
    result[0] = str(Path('Q:/')/WORK.relative_to(ROOT)/'runtime/qemu-system-arm.exe')
    return result


def permanent_points(c):
    return {x for p in c['roles'].values() for x in [p['start'], p['checkpoint']]+p['returns']}


# No global ledger/contract mutation: callers supply the contract explicitly.
def entry_points(pairs, c):
    return {check_prepared(s['prepared'], c['roles'][s['role']])['entry_pc']
            for s in pairs if s['prepared'] is not None and s['entered'] is None}


def run(output, max_calls=16, guest_seconds=2, wall_seconds=180):
    output = output.resolve()
    require(output.is_relative_to(OUTPUT) and not output.exists() and
            not output.with_suffix('.qemu.log').exists(), 'Use new r15 evidence output')
    require(type(max_calls) is int and 8 <= max_calls <= 128 and 1 <= guest_seconds <= 6 and
            30 <= wall_seconds <= 300, 'Invalid observation bounds')
    identity = model_identity(); c, images = collect(), read_inputs()
    buf = ctypes.create_unicode_buffer(32768)
    require(not ctypes.windll.kernel32.QueryDosDeviceW('Q:', buf, len(buf)), 'Q: already occupied')
    require(not subprocess.check_output(['powershell.exe', '-NoProfile', '-Command',
        "Get-CimInstance Win32_Process -Filter \"name like 'qemu%'\" | Select-Object -ExpandProperty ProcessId"],
        encoding='utf-8').strip(), 'Existing QEMU is running')
    r = dict(schema=1, tool=TOOL, created_at=datetime.now(timezone.utc).isoformat(), completed=False,
        **identity, contract=c, firmware_inputs=c['inputs'], sources={n:sha((ROOT/n).read_bytes()) for n in SOURCES},
        firmware_loaded=True, reset_pc_initialized_by_qemu_loader=True, breakpoint_timing_perturbed=True,
        default_completion_logic_disabled=False, controller_link_enabled=False,
        owned_shutdown='QMP quit; NOT camera normal shutdown', max_calls=max_calls,
        guest_target_seconds=guest_seconds, wall_limit_seconds=wall_seconds, events=[], pairs=[], pauses=[],
        **{n:False for n in FALSE_FIELDS})
    process = remote = session = sock = stream = None
    error = row = None; active = permanent_points(c); own_alias = False
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as evidence:
        try:
            subprocess.run(['subst.exe', 'Q:', str(ROOT)], check=True); own_alias = True
            require(Path('Q:/').samefile(ROOT), 'Workspace alias differs')
            ports = free_port(), free_port(); r['command'] = cmd = command(ports)
            env = dict(os.environ, TEMP=os.environ['PI_SCRATCH_DIR'], TMP=os.environ['PI_SCRATCH_DIR'],
                       TMPDIR=os.environ['PI_SCRATCH_DIR'], PYTHONDONTWRITEBYTECODE='1')
            with output.with_suffix('.qemu.log').open('xb') as log:
                process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=log, env=env)
            r['owned_pid'] = process.pid; sock = connect(ports[1], process); sock.settimeout(15)
            stream = sock.makefile('rwb'); json.loads(stream.readline()); session = BootSession(); session.qmp = stream
            session.query('qmp_capabilities'); remote = BootRemote(ports[0])
            r['model_tree'] = session.query('human-monitor-command', {'command-line':'info qtree'})
            for pc in sorted(active): remote.breakpoint(pc)
            start = time.monotonic(); r['trace_stop_reason'] = 'event-bound'
            for index in range(8*(max_calls+64)):
                remaining = wall_seconds-(time.monotonic()-start)
                if remaining <= 0: r['trace_stop_reason'] = 'wall-bound'; break
                remote.sock.settimeout(min(15, remaining))
                try: stop = remote.command('c')
                except socket.timeout:
                    remote.sock.settimeout(15); stop = remote.interrupt()
                    r['pauses'].append(dict(phase='trace', stop=stop, ticks=ticks(remote)))
                    r['trace_stop_reason'] = 'quiet-bound'; break
                remote.sock.settimeout(15); require(stop.startswith('T05'), 'Unexpected original launch stop')
                previous = remote.command('qC'); tid = stopped_thread(stop, previous); remote.select_thread(int(tid,16))
                packet = remote.regs(); regs = {n:remote.get(packet,n) for n in REGISTERS}; pc = regs['pc']
                head = remote.read(BASE, 0x6C); roles = [role for role,img in images.items() if head == img[:0x6C]]
                require(len(roles) == 1 and pc in active, 'Unknown original role/breakpoint')
                role = roles[0]; p = c['roles'][role]; local = (int(tid,16)-1)%2
                row = dict(sequence=index, role=role, thread=tid, local_cpu=local, stop=stop,
                    previous_selected_thread=previous, registers=regs, image_head=head.hex(),
                    rom_window=dict(address=pc-16, bytes=remote.read(pc-16,32).hex()),
                    system={n:remote.read_register(n) for n in SYSTEM}, model_ticks=selected_ticks(remote,tid),
                    current=list(struct.unpack('<2I',remote.read(p['context']['current'],8))))
                phase, pi = classify(r['pairs'], row, p); row.update(phase=phase, pair_index=pi)
                if phase == 'input':
                    require(len(r['pairs']) < max_calls+64, 'Prepared call overflow')
                    row['table_words'] = list(struct.unpack('<2I',remote.read(p['table_global'],8)))
                    base,count = row['table_words']; idx = regs['r0'] & 0xFFFF
                    require(0 < idx <= count <= 65535, 'Outside natural table-index sample')
                    tb = base+(idx-1)*216; require(bounded_ram(p['context'],tb,216), 'Unbounded table TCB')
                    row.update(tcb_address=tb, tcb=remote.read(tb,216).hex()); check_input(row,p)
                elif phase == 'prepared':
                    tb,fp = regs['r4'],regs['r0']
                    require(bounded_ram(p['context'],tb,216) and bounded_ram(p['context'],fp,76), 'Unbounded publish')
                    row.update(tcb_address=tb,tcb=remote.read(tb,216).hex(),frame_address=fp,frame=remote.read(fp,76).hex())
                    require(bounded_stack(p,regs['sp'],40), 'Unbounded publish saved stack')
                    row['saved_stack'] = remote.read(regs['sp'],40).hex()
                    entry = check_prepared(row,p)['entry_pc']
                    require(entry not in permanent_points(c), 'Entry/permanent conflict')
                    if entry not in active: remote.breakpoint(entry); active.add(entry)
                elif phase == 'returned':
                    require(bounded_stack(p,regs['sp'],40), 'Unbounded return stack')
                    row['saved_stack'] = remote.read(regs['sp'],40).hex()
                elif phase == 'entered':
                    tb = row['current'][local]; require(bounded_ram(p['context'],tb,216), 'Unbounded first-entry TCB')
                    row.update(tcb_address=tb,tcb=remote.read(tb,216).hex())
                remote.select_thread(int(tid,16)); row['step_reply'] = advance_isolated(remote,pc,tid,True)
                remote.select_thread(int(tid,16)); packet = remote.regs()
                row['after_registers'] = {n:remote.get(packet,n) for n in REGISTERS}
                row['after_system'] = {n:remote.read_register(n) for n in SYSTEM}
                if phase == 'input': row['after_stack'] = remote.read(row['after_registers']['sp'],40).hex()
                if phase == 'returned':
                    target = row['after_registers']['pc']; require(BASE+16 <= target < BASE+len(images[role])-18, 'Return outside ROM')
                    row['return_rom'] = dict(address=target-16, bytes=remote.read(target-16,32).hex())
                ingest(r['pairs'],row,p); r['events'].append(row)
                if phase == 'entered' and pc not in entry_points(r['pairs'],c):
                    remote.breakpoint(pc,False); active.remove(pc)
                if ready(r['pairs'],max_calls): r['trace_stop_reason'] = 'sample-bound-drained'; break
            r['pending'] = [s['sequence'] for s in r['pairs'] if not complete(s)]
            for pc in sorted(active): remote.breakpoint(pc,False)
            r['trace_end_ticks'] = ticks(remote)
            while ticks(remote) < guest_seconds*48000000:
                remaining = wall_seconds-(time.monotonic()-start)
                if remaining <= 0: break
                remote.sock.settimeout(min(15,remaining))
                try: stop = remote.command('c')
                except socket.timeout: remote.sock.settimeout(15); stop = remote.interrupt()
                remote.sock.settimeout(15); require(stop.startswith('T02'), 'Unexpected untraced stop')
                r['pauses'].append(dict(phase='untraced',stop=stop,ticks=ticks(remote)))
            r['final_ticks'] = ticks(remote); r['guest_target_reached'] = r['final_ticks'] >= guest_seconds*48000000
            r['final_cpus'] = sample(remote,images); r['final_status'] = session.query('query-status')
            if ready(r['pairs'],max_calls): r['summary'] = summarize(r['pairs'])
            r['wall_seconds'] = time.monotonic()-start; r['completed'] = True
        except Exception as exc:
            error = exc; r['failure'] = type(exc).__name__+': '+str(exc)
            if row is not None: r['failure_event'] = row
        finally:
            try:
                if process is not None and process.poll() is None and session is not None:
                    r['quit_receipt'] = quit_owned(session,process)
            except Exception as exc: r['quit_failure'] = type(exc).__name__+': '+str(exc)
            finally:
                if process is not None and process.poll() is None:
                    process.terminate()
                    try: process.wait(timeout=10)
                    except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=10)
                    r['forced_host_cleanup'] = True
                r['exit_code'] = None if process is None else process.returncode
                r['owned_process_closed'] = process is not None and process.poll() is not None
                r['rsp_commands'] = getattr(remote,'audit',[]); r['rsp_controls'] = getattr(remote,'controls',[])
                r['qmp_commands'] = getattr(session,'audit',[])
                r['close_notes'] = close_handles([getattr(remote,'sock',None),stream,sock])
                if own_alias:
                    require(Path('Q:/').samefile(ROOT),'Owned alias changed before removal')
                    subprocess.run(['subst.exe','Q:','/D'],check=True)
                r['mapping_removed'] = not bool(ctypes.windll.kernel32.QueryDosDeviceW('Q:',buf,len(buf)))
                log = output.with_suffix('.qemu.log'); r['log_sha256'] = sha(log.read_bytes()) if log.exists() else None
                json.dump(r,evidence,indent=2); evidence.write('\n')
    if error is not None: raise error
    print(r['trace_stop_reason'], 'calls',len(r['pairs']),'pending',r['pending'],flush=True)
    return r


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--max-calls',type=int,default=16); ap.add_argument('--guest-seconds',type=float,default=2)
    ap.add_argument('--wall-seconds',type=int,default=180); args=ap.parse_args()
    run(args.output,args.max_calls,args.guest_seconds,args.wall_seconds)
