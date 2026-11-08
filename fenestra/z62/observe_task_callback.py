"""Observe original LDR/BX field targets and first instructions, without injected calls."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import time
from observe_task_entry import (ROOT, BASE, QEMU_REL, QEMU_SHA, REGISTERS, SYSTEM, free_port,
    connect, stopped_thread, BootSession, BootRemote, build_command, sample, ticks,
    selected_ticks, advance_isolated, quit_owned, close_handles, sha, require, read_inputs,
    FALSE_FIELDS, SOURCES as OLD_SOURCES)
from task_callback_contract import (TOOL, LIMITATIONS, collect, check_prepared, check_pair,
    summarize, bounded_read, check_shared, bx_effect, first_effect)
from task_context import bounded_ram
SOURCES=tuple(sorted(set(OLD_SOURCES+('fenestra/z62/observe_task_callback.py','fenestra/z62/task_callback_contract.py'))))


def registers(remote,tid):
    remote.select_thread(int(tid,16));packet=remote.regs()
    return {n:remote.get(packet,n) for n in REGISTERS}


def plain_step(remote,tid):
    remote.select_thread(int(tid,16));reply=remote.command('vCont;s:'+tid)
    require(reply.startswith('T05') and stopped_thread(reply,remote.command('qC'))==tid,'Target step CPU differs')
    return reply


def run(output,max_entries=32,guest_seconds=2,wall_seconds=180):
    output=output.resolve();require(output.is_relative_to(ROOT/'analysis') and not output.exists(),'Use new analysis output')
    require(type(max_entries) is int and 8<=max_entries<=256 and 1<=guest_seconds<=6 and 30<=wall_seconds<=300,'Invalid bounds')
    root=Path('Q:/');require(root.is_dir() and root.samefile(ROOT),'Verified Q: alias required')
    require(sha((root/QEMU_REL).read_bytes())==QEMU_SHA,'Pinned QEMU changed')
    contract,images=collect(),read_inputs();ports=free_port(),free_port();require(ports[0]!=ports[1],'Port collision')
    command=build_command(root,'minimal',*ports)
    record=dict(schema=1,tool=TOOL,created_at=datetime.now(timezone.utc).isoformat(),completed=False,command=command,
        qemu_sha256=QEMU_SHA,contract=contract,sources={n:sha((ROOT/n).read_bytes()) for n in SOURCES},
        firmware_loaded=True,reset_pc_initialized_by_qemu_loader=True,breakpoint_timing_perturbed=True,
        controller_loaded=False,controller_link_enabled=False,owned_shutdown='QMP quit; NOT camera normal shutdown',
        max_entries=max_entries,guest_target_seconds=guest_seconds,wall_limit_seconds=wall_seconds,
        events=[],pairs=[],pauses=[],**{n:False for n in FALSE_FIELDS+LIMITATIONS})
    output.parent.mkdir(parents=True,exist_ok=True);log_path=output.with_suffix('.qemu.log');require(not log_path.exists(),'Log exists')
    process=remote=session=qmp_sock=qmp_stream=None;error=row=None;pending=[]
    permanent={p['checkpoint'] for p in contract['roles'].values()};active=set(permanent)
    with output.open('x',encoding='utf-8') as evidence:
        try:
            env=dict(os.environ,TEMP=os.environ['PI_SCRATCH_DIR'],TMP=os.environ['PI_SCRATCH_DIR'],TMPDIR=os.environ['PI_SCRATCH_DIR'],PYTHONDONTWRITEBYTECODE='1')
            with log_path.open('xb') as log:process=subprocess.Popen(command,stdout=subprocess.DEVNULL,stderr=log,env=env)
            record['owned_pid']=process.pid;qmp_sock=connect(ports[1],process);qmp_sock.settimeout(15);qmp_stream=qmp_sock.makefile('rwb')
            session=BootSession();session.qmp=qmp_stream;json.loads(qmp_stream.readline());session.query('qmp_capabilities')
            remote=BootRemote(ports[0]);record['model_tree']=session.query('human-monitor-command',{'command-line':'info qtree'})
            for pc in sorted(active):remote.breakpoint(pc)
            start=time.monotonic();record['trace_stop_reason']='event-bound'
            for index in range(4*(max_entries+64)):
                remaining=wall_seconds-(time.monotonic()-start)
                if remaining<=0:record['trace_stop_reason']='wall-bound';break
                remote.sock.settimeout(min(15,remaining))
                try:stop=remote.command('c')
                except socket.timeout:
                    remote.sock.settimeout(15);stop=remote.interrupt();record['pauses'].append(dict(phase='trace',stop=stop,ticks=ticks(remote)))
                    require(stop.startswith('T02'),'Unexpected trace pause');record['trace_stop_reason']='quiet-bound';break
                remote.sock.settimeout(15);require(stop.startswith('T05'),'Unexpected original entry stop')
                previous=remote.command('qC');tid=stopped_thread(stop,previous);regs=registers(remote,tid);head=remote.read(BASE,0x6C)
                roles=[r for r,img in images.items() if head==img[:0x6C]];require(len(roles)==1,'Missing original role')
                role=roles[0];p=contract['roles'][role];pc=regs['pc'];local=(int(tid,16)-1)%2
                row=dict(sequence=index,role=role,thread=tid,local_cpu=local,stop=stop,previous_selected_thread=previous,
                    registers=regs,image_head=head.hex(),rom_window=dict(address=pc-16,bytes=remote.read(pc-16,32).hex()),
                    system={n:remote.read_register(n) for n in SYSTEM},model_ticks=selected_ticks(remote,tid),
                    current=list(struct.unpack('<2I',remote.read(p['context']['current'],8))))
                require(row['rom_window']['bytes']==images[role][pc-BASE-16:pc-BASE+16].hex(),'Original runtime ROM changed')
                pair=None
                if pc==p['checkpoint']:
                    tb,fp=regs['r4'],regs['r0'];require(bounded_ram(p['context'],tb,216) and bounded_ram(p['context'],fp,76),'Unbounded TCB/frame')
                    row.update(phase='prepared',tcb_address=tb,tcb=remote.read(tb,216).hex(),frame_address=fp,frame=remote.read(fp,76).hex())
                    row['prepared_analysis']=a=check_prepared(row,p)
                    require(not any(s['role']==role and s['prepared']['tcb_address']==tb for s in pending),'Ambiguous live target TCB')
                    require(len(record['pairs'])<max_entries+64,'Pending launch overflow')
                    pair=dict(sequence=len(record['pairs']),role=role,prepared=row,entered=None)
                    record['pairs'].append(pair);pending.append(pair);entry=a['entry_pc']
                    require(entry not in permanent,'Entry/permanent breakpoint conflict')
                    if entry not in active:remote.breakpoint(entry);active.add(entry)
                else:
                    matches=[s for s in pending if s['role']==role and s['prepared']['tcb_address']==row['current'][local] and
                             s['prepared']['prepared_analysis']['entry_pc']==pc]
                    require(len(matches)<=1,'Ambiguous first task entry')
                    if matches:
                        pair=matches[0];tb=row['current'][local];require(bounded_ram(p['context'],tb,216),'Unbounded current target')
                        row.update(phase='entered',tcb_address=tb,tcb=remote.read(tb,216).hex())
                        pair['entered']=row;pair['analysis']=check_pair(pair,p);pending.remove(pair)
                        if regs['cpsr']&32:
                            require(pc==p['shared_entry'] and bounded_read(p,regs['r1'],8),'Unbounded original shared descriptor')
                            row['callback']=dict(descriptor_address=regs['r1'],descriptor=remote.read(regs['r1'],8).hex())
                    else:
                        require(pc in active,'Unregistered first-entry breakpoint');row.update(phase='unmatched-entry')
                row['pair_index']=None if pair is None else pair['sequence']
                remote.select_thread(int(tid,16));row['step_reply']=advance_isolated(remote,pc,tid,True)
                row['after_registers']=registers(remote,tid)
                if 'callback' in row:
                    cb=row['callback'];field=struct.unpack('<2I',bytes.fromhex(cb['descriptor']))[1];a=row['after_registers']
                    require(a==dict(regs,pc=pc+2,r1=field),'Independent LDR field mismatch')
                    expected_bx=bx_effect(a);target=expected_bx['pc']
                    require(BASE+16<=target and target+16<=BASE+len(images[role])-2,'Unbounded target ROM')
                    cb['bx_reply']=plain_step(remote,tid);cb['after_bx']=registers(remote,tid)
                    require(cb['after_bx']==expected_bx,'Actual BX target differs')
                    cb['target_rom']=dict(address=target,bytes=remote.read(target,16).hex())
                    require(cb['target_rom']['bytes']==images[role][target-BASE:target-BASE+16].hex(),'Original target ROM differs')
                    cb['target_current']=list(struct.unpack('<2I',remote.read(p['context']['current'],8)))
                    cb['target_system']={n:remote.read_register(n) for n in SYSTEM}
                    expected,stack,kind=first_effect(cb['after_bx'],bytes.fromhex(cb['target_rom']['bytes']))
                    if stack:require(bounded_read(p,stack['address'],len(bytes.fromhex(stack['bytes']))),'Unbounded target PUSH read')
                    cb['target_step_reply']=plain_step(remote,tid);cb['after_target']=registers(remote,tid)
                    cb['stack_write']=None if stack is None else dict(address=stack['address'],bytes=remote.read(stack['address'],len(bytes.fromhex(stack['bytes']))).hex())
                    cb['after_system']={n:remote.read_register(n) for n in SYSTEM}
                    row['callback_analysis']=check_shared(row,p)
                if row['phase']=='entered' and not any(s['prepared']['prepared_analysis']['entry_pc']==pc for s in pending):
                    remote.breakpoint(pc,False);active.remove(pc)
                record['events'].append(row);finished=sum(s['entered'] is not None for s in record['pairs'])
                if finished>=max_entries and not pending:record['trace_stop_reason']='sample-bound-drained';break
            record['pending']=[s['sequence'] for s in pending]
            for pc in sorted(active):remote.breakpoint(pc,False)
            record['trace_end_ticks']=ticks(remote)
            while ticks(remote)<guest_seconds*48000000:
                remaining=wall_seconds-(time.monotonic()-start)
                if remaining<=0:break
                remote.sock.settimeout(min(15,remaining))
                try:stop=remote.command('c')
                except socket.timeout:remote.sock.settimeout(15);stop=remote.interrupt()
                remote.sock.settimeout(15);require(stop.startswith('T02'),'Unexpected untraced stop')
                record['pauses'].append(dict(phase='untraced',stop=stop,ticks=ticks(remote)))
            record['final_ticks']=ticks(remote);record['guest_target_reached']=record['final_ticks']>=guest_seconds*48000000
            record['final_cpus']=sample(remote,images);record['final_status']=session.query('query-status')
            if not pending:record['summary']=summarize(record['pairs'],contract)
            record['wall_seconds']=time.monotonic()-start;record['quit_receipt']=quit_owned(session,process);record['completed']=True
        except Exception as exc:
            error=exc;record['failure']=type(exc).__name__+': '+str(exc)
            if row is not None:record['failure_event']=row
        finally:
            if process is not None and process.poll() is None and session is not None:
                try:record['quit_receipt']=quit_owned(session,process)
                except Exception as exc:record['quit_failure']=type(exc).__name__+': '+str(exc)
            if process is not None and process.poll() is None:
                process.terminate()
                try:process.wait(timeout=10)
                except subprocess.TimeoutExpired:process.kill();process.wait(timeout=10)
            record['exit_code']=None if process is None else process.returncode;record['owned_process_closed']=process is not None and process.poll() is not None
            record['rsp_commands']=getattr(remote,'audit',[]);record['rsp_controls']=getattr(remote,'controls',[]);record['qmp_commands']=getattr(session,'audit',[])
            record['close_notes']=close_handles([getattr(remote,'sock',None),qmp_stream,qmp_sock]);record['log_sha256']=sha(log_path.read_bytes()) if log_path.exists() else None
            json.dump(record,evidence,indent=2);evidence.write('\n')
    if error is not None:raise error
    require(record['exit_code']==0 and record['owned_process_closed'],'Owned process not closed')
    print('callback trace',record['trace_stop_reason'],'pairs',len(record['pairs']),'pending',record['pending'],flush=True)
    return record


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--max-entries',type=int,default=32)
    p.add_argument('--guest-seconds',type=float,default=2);p.add_argument('--wall-seconds',type=int,default=180);a=p.parse_args();run(a.output,a.max_entries,a.guest_seconds,a.wall_seconds)
