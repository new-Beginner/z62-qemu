"""Observe natural stock task creation without injected calls or debugger writes."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket
import subprocess
import time

from startup_contract import ROOT, BASE, require, sha, read_inputs
from pool_calls import REGISTERS, SYSTEM
from observe_startup import QEMU_REL, QEMU_SHA, free_port, connect, stopped_thread
from observe_pool import advance_isolated, quit_owned, close_handles
from observe_boot_wait import BootRemote, BootSession, build_command, sample, FALSE_FIELDS
from observe_task_context import ticks
from observe_wait_store import SOURCES as PRIOR_SOURCES
from task_create_contract import TOOL, LIMITATIONS, collect, bounded_read, bounded_ram, check_pair, summarize

SOURCES = tuple(sorted(set(PRIOR_SOURCES + ('fenestra/z62/observe_task_create.py',
                                            'fenestra/z62/task_create_contract.py'))))

def matching_returns(pending, role, tid, regs):
    return [s for s in pending if s['role']==role and s['thread']==tid and
            s['entry']['registers']['sp']==regs['sp'] and
            s['entry']['registers']['lr']&~1==regs['pc']]


def selected_ticks(remote, tid):
    """Clock helper selects CPU01; restore the stopped engine before further reads."""
    try:
        return ticks(remote)
    finally:
        remote.select_thread(int(tid, 16))



def run(output, max_calls=64, guest_seconds=2, wall_seconds=180):
    output=output.resolve()
    require(output.is_relative_to(ROOT/'analysis') and not output.exists(),'Use new analysis output')
    require(type(max_calls) is int and 8<=max_calls<=512 and 1<=guest_seconds<=6 and
            30<=wall_seconds<=300,'Invalid observation bounds')
    root=Path('Q:/');require(root.is_dir() and root.samefile(ROOT),'Verified Q: alias required')
    require(sha((root/QEMU_REL).read_bytes())==QEMU_SHA,'Pinned model changed')
    contract,images=collect(),read_inputs()
    ports=free_port(),free_port();command=build_command(root,'minimal',*ports)
    record=dict(schema=1,tool=TOOL,created_at=datetime.now(timezone.utc).isoformat(),completed=False,
        command=command,qemu_sha256=QEMU_SHA,contract=contract,
        sources={n:sha((ROOT/n).read_bytes()) for n in SOURCES},
        max_calls=max_calls,guest_target_seconds=guest_seconds,wall_limit_seconds=wall_seconds,
        firmware_loaded=True,reset_pc_initialized_by_qemu_loader=True,breakpoint_timing_perturbed=True,
        controller_loaded=False,controller_link_enabled=False,
        owned_shutdown='QMP quit; NOT camera normal shutdown',events=[],pairs=[],pauses=[],
        **{n:False for n in FALSE_FIELDS+LIMITATIONS})
    output.parent.mkdir(parents=True,exist_ok=True);log_path=output.with_suffix('.qemu.log')
    require(not log_path.exists(),'Log already exists')
    process=remote=session=qmp_sock=qmp_stream=None;error=row=None
    pending=[]
    permanent={p[k] for p in contract['roles'].values() for k in ('entry','constructed')}
    active=set(permanent)
    with output.open('x',encoding='utf-8') as evidence:
        try:
            env=dict(os.environ,TEMP=os.environ['PI_SCRATCH_DIR'],TMP=os.environ['PI_SCRATCH_DIR'],
                     TMPDIR=os.environ['PI_SCRATCH_DIR'],PYTHONDONTWRITEBYTECODE='1')
            with log_path.open('xb') as log:
                process=subprocess.Popen(command,stdout=subprocess.DEVNULL,stderr=log,env=env)
            record['owned_pid']=process.pid
            qmp_sock=connect(ports[1],process);qmp_sock.settimeout(15);qmp_stream=qmp_sock.makefile('rwb')
            session=BootSession();session.qmp=qmp_stream
            json.loads(qmp_stream.readline());session.query('qmp_capabilities')
            remote=BootRemote(ports[0])
            record['model_tree']=session.query('human-monitor-command',{'command-line':'info qtree'})
            for pc in sorted(active):remote.breakpoint(pc)
            start=time.monotonic();record['trace_stop_reason']='event-bound'
            for index in range(6*(max_calls+64)):
                remaining=wall_seconds-(time.monotonic()-start)
                if remaining<=0:record['trace_stop_reason']='wall-bound';break
                remote.sock.settimeout(min(15,remaining))
                try:stop=remote.command('c')
                except socket.timeout:
                    remote.sock.settimeout(15);stop=remote.interrupt()
                    record['pauses'].append(dict(phase='trace',stop=stop,ticks=ticks(remote)))
                    require(stop.startswith('T02'),'Unexpected quiet pause')
                    record['trace_stop_reason']='quiet-bound';break
                remote.sock.settimeout(15);require(stop.startswith('T05'),'Unexpected creation breakpoint')
                previous=remote.command('qC');tid=stopped_thread(stop,previous);remote.select_thread(int(tid,16))
                packet=remote.regs();regs={n:remote.get(packet,n) for n in REGISTERS}
                head=remote.read(BASE,0x6C);roles=[r for r,img in images.items() if head==img[:0x6C]]
                require(len(roles)==1,'Missing original role identity')
                role=roles[0];p=contract['roles'][role];pc=regs['pc']
                row=dict(sequence=index,role=role,thread=tid,stop=stop,previous_selected_thread=previous,
                    registers=regs,image_head=head.hex(),
                    rom_window=dict(address=pc-16,bytes=remote.read(pc-16,32).hex()),
                    system={n:remote.read_register(n) for n in SYSTEM},model_ticks=selected_ticks(remote,tid))
                require(row['rom_window']['bytes']==images[role][pc-BASE-16:pc-BASE+16].hex(),'Original runtime ROM changed')
                if pc==p['entry']:
                    require(bounded_read(p,regs['r0'],56),'Unbounded original config')
                    row.update(phase='entry',config=remote.read(regs['r0'],56).hex())
                    pair=dict(sequence=len(record['pairs']),role=role,thread=tid,entry=row,constructed=None,returned=None)
                    require(all(not (s['role']==role and s['entry']['registers']['sp']==regs['sp']) for s in pending),
                            'Ambiguous live caller stack')
                    record['pairs'].append(pair);pending.append(pair)
                    ret=regs['lr']&~1
                    require(BASE+16<=ret<BASE+len(images[role])-18 and ret not in permanent,'Unbounded/conflicting native return')
                    if ret not in active:remote.breakpoint(ret);active.add(ret)
                elif pc==p['constructed']:
                    matches=[s for s in pending if s['role']==role and s['thread']==tid and
                             s['entry']['registers']['sp']==regs['sp']+56]
                    require(len(matches)==1 and matches[0]['constructed'] is None,'Unpaired initial task frame')
                    pair=matches[0];tcb=regs['r4'];fp=regs['r0']
                    require(bounded_ram(p['context'],tcb,216) and bounded_ram(p['context'],fp,76),'Unbounded native TCB/frame')
                    row.update(phase='constructed',tcb_address=tcb,tcb=remote.read(tcb,216).hex(),
                        frame_address=fp,frame=remote.read(fp,76).hex(),
                        config=remote.read(pair['entry']['registers']['r0'],56).hex())
                    pair['constructed']=row
                else:
                    matches=matching_returns(pending,role,tid,regs)
                    require(len(matches)<=1,'Ambiguous original constructor return')
                    if matches:
                        pair=matches[0];row.update(phase='returned',tcb=None if pair['constructed'] is None else
                            remote.read(pair['constructed']['tcb_address'],216).hex())
                        pair['returned']=row;pair['analysis']=check_pair(pair,p);pending.remove(pair)
                    else:
                        require(pc in active and pc not in permanent and
                            any(s['entry']['registers']['lr']&~1==pc for s in pending),
                            'Unregistered original stop')
                        pair=None;row.update(phase='unmatched-return')
                row['pair_index']=None if pair is None else pair['sequence']
                remote.select_thread(int(tid,16))
                row['step_reply']=advance_isolated(remote,pc,tid,True)
                remote.select_thread(int(tid,16));packet=remote.regs()
                row['after_registers']={n:remote.get(packet,n) for n in REGISTERS}
                if row['phase']=='returned' and not any(s['entry']['registers']['lr']&~1==pc for s in pending):
                    remote.breakpoint(pc,False);active.remove(pc)
                record['events'].append(row)
                finished=sum(s['returned'] is not None for s in record['pairs'])
                if row['phase']=='returned' and finished%64==0:print('native creation returns',finished,flush=True)
                if finished>=max_calls and not pending:record['trace_stop_reason']='sample-bound-drained';break
            record['pending']=[s['sequence'] for s in pending]
            for pc in sorted(active):remote.breakpoint(pc,False)
            record['trace_end_ticks']=ticks(remote)
            while ticks(remote)<guest_seconds*48000000:
                remaining=wall_seconds-(time.monotonic()-start)
                if remaining<=0:break
                remote.sock.settimeout(min(15,remaining))
                try:stop=remote.command('c')
                except socket.timeout:
                    remote.sock.settimeout(15);stop=remote.interrupt()
                remote.sock.settimeout(15);require(stop.startswith('T02'),'Unexpected untraced stop')
                record['pauses'].append(dict(phase='untraced',stop=stop,ticks=ticks(remote)))
            record['final_ticks']=ticks(remote)
            record['guest_target_reached']=record['final_ticks']>=guest_seconds*48000000
            record['final_cpus']=sample(remote,images)
            record['final_status']=session.query('query-status')
            if not pending:record['summary']=summarize(record['pairs'],contract)
            record['wall_seconds']=time.monotonic()-start
            record['quit_receipt']=quit_owned(session,process);record['completed']=True
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
            record['exit_code']=None if process is None else process.returncode
            record['owned_process_closed']=process is not None and process.poll() is not None
            record['rsp_commands']=getattr(remote,'audit',[]);record['rsp_controls']=getattr(remote,'controls',[])
            record['qmp_commands']=getattr(session,'audit',[])
            record['close_notes']=close_handles([getattr(remote,'sock',None),qmp_stream,qmp_sock])
            record['log_sha256']=sha(log_path.read_bytes()) if log_path.exists() else None
            json.dump(record,evidence,indent=2);evidence.write('\n')
    if error is not None:raise error
    require(record['exit_code']==0 and record['owned_process_closed'],'Owned process not closed')
    print('creation trace',record['trace_stop_reason'],'pairs',len(record['pairs']),'pending',record['pending'],flush=True)
    return record


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--max-calls',type=int,default=64)
    parser.add_argument('--guest-seconds',type=float,default=2);parser.add_argument('--wall-seconds',type=int,default=180)
    args=parser.parse_args();run(args.output,args.max_calls,args.guest_seconds,args.wall_seconds)
