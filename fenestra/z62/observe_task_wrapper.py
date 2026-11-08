"""Trace natural wrapper calls only. No guest writes, injected calls or success events."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket
import subprocess
import time
from observe_task_callback import (ROOT,BASE,QEMU_REL,QEMU_SHA,REGISTERS,SYSTEM,free_port,connect,stopped_thread,
    BootSession,BootRemote,build_command,sample,ticks,selected_ticks,advance_isolated,quit_owned,close_handles,
    sha,require,read_inputs,FALSE_FIELDS,registers,SOURCES as OLD_SOURCES)
from task_wrapper_contract import TOOL,LIMITATIONS,PHASES,collect,bounded_read,read_plan,matching,check_pair,summarize,step_effect,sample_ready
SOURCES=tuple(sorted(set(OLD_SOURCES+('fenestra/z62/observe_task_wrapper.py','fenestra/z62/task_wrapper_contract.py'))))


def run(output,max_calls=24,guest_seconds=2,wall_seconds=180):
    output=output.resolve();require(output.is_relative_to(ROOT/'analysis') and not output.exists(),'Use new analysis output')
    require(type(max_calls) is int and 8<=max_calls<=128 and 1<=guest_seconds<=6 and 30<=wall_seconds<=300,'Invalid bounds')
    root=Path('Q:/');require(root.is_dir() and root.samefile(ROOT),'Verified Q: alias required')
    require(sha((root/QEMU_REL).read_bytes())==QEMU_SHA,'Pinned model changed')
    c,images=collect(),read_inputs();g,q=free_port(),free_port();require(g!=q,'Port collision');cmd=build_command(root,'minimal',g,q)
    record=dict(schema=1,tool=TOOL,created_at=datetime.now(timezone.utc).isoformat(),completed=False,command=cmd,
        qemu_sha256=QEMU_SHA,contract=c,sources={n:sha((ROOT/n).read_bytes()) for n in SOURCES},
        firmware_loaded=True,reset_pc_initialized_by_qemu_loader=True,breakpoint_timing_perturbed=True,
        controller_loaded=False,controller_link_enabled=False,owned_shutdown='QMP quit; NOT camera normal shutdown',
        max_calls=max_calls,guest_target_seconds=guest_seconds,wall_limit_seconds=wall_seconds,
        events=[],pairs=[],pauses=[],**{n:False for n in FALSE_FIELDS+LIMITATIONS})
    output.parent.mkdir(parents=True,exist_ok=True);log_path=output.with_suffix('.qemu.log');require(not log_path.exists(),'Log exists')
    process=remote=session=qs=qstream=None;error=row=None;active={pc for p in c['roles'].values() for pc in p['points'].values()}
    with output.open('x',encoding='utf-8') as evidence:
        try:
            env=dict(os.environ,TEMP=os.environ['PI_SCRATCH_DIR'],TMP=os.environ['PI_SCRATCH_DIR'],TMPDIR=os.environ['PI_SCRATCH_DIR'],PYTHONDONTWRITEBYTECODE='1')
            with log_path.open('xb') as log:process=subprocess.Popen(cmd,stdout=subprocess.DEVNULL,stderr=log,env=env)
            record['owned_pid']=process.pid;qs=connect(q,process);qs.settimeout(15);qstream=qs.makefile('rwb')
            session=BootSession();session.qmp=qstream;json.loads(qstream.readline());session.query('qmp_capabilities')
            remote=BootRemote(g);record['model_tree']=session.query('human-monitor-command',{'command-line':'info qtree'})
            for pc in sorted(active):remote.breakpoint(pc)
            start=time.monotonic();record['trace_stop_reason']='event-bound'
            for index in range(32*(max_calls+32)):
                remaining=wall_seconds-(time.monotonic()-start)
                if remaining<=0:record['trace_stop_reason']='wall-bound';break
                remote.sock.settimeout(min(15,remaining))
                try:stop=remote.command('c')
                except socket.timeout:
                    remote.sock.settimeout(15);stop=remote.interrupt();record['pauses'].append(dict(phase='trace',stop=stop,ticks=ticks(remote)))
                    require(stop.startswith('T02'),'Unexpected trace pause');record['trace_stop_reason']='quiet-bound';break
                remote.sock.settimeout(15);require(stop.startswith('T05'),'Unexpected wrapper stop')
                previous=remote.command('qC');tid=stopped_thread(stop,previous);r=registers(remote,tid);head=remote.read(BASE,0x6C)
                roles=[role for role,img in images.items() if img[:0x6C]==head];require(len(roles)==1,'Missing original engine')
                role=roles[0];p=c['roles'][role];pc=r['pc'];phases=[k for k,v in p['points'].items() if v==pc];require(len(phases)==1,'Unregistered wrapper stop');phase=phases[0]
                row=dict(sequence=index,role=role,thread=tid,phase=phase,stop=stop,previous_selected_thread=previous,
                    registers=r,image_head=head.hex(),rom_window=dict(address=pc-16,bytes=remote.read(pc-16,32).hex()),
                    system={n:remote.read_register(n) for n in SYSTEM},model_ticks=selected_ticks(remote,tid),memory={})
                require(row['rom_window']['bytes']==images[role][pc-BASE-16:pc-BASE+16].hex(),'Original ROM changed')
                if phase=='entry':
                    require(len(record['pairs'])<max_calls+32,'Wrapper preparation bound')
                    pair=dict(sequence=len(record['pairs']),role=role,stages={});record['pairs'].append(pair)
                else:pair=matching(record['pairs'],record['events'],role,phase,r)
                row['pair_index']=None if pair is None else pair['sequence']
                for label,address,size in read_plan(p,phase,r,pair,record['events']):
                    require(bounded_read(p,address,size),'Unbounded wrapper read: '+label);row['memory'][label]=remote.read(address,size).hex()
                if pair is not None:pair['stages'][phase]=index
                row['step_reply']=advance_isolated(remote,pc,tid,True);row['after_registers']=registers(remote,tid)
                handle=int.from_bytes(bytes.fromhex(row['memory']['handle_word']),'little') if phase=='constructed' else None
                require(row['after_registers']==step_effect(r,p,phase,handle),'Original wrapper step effect differs')
                if pair is not None and phase in ('created','field'):
                    row['object_after']=remote.read(r['r4'],32).hex()
                record['events'].append(row)
                if phase=='started' and pair is not None:pair['analysis']=check_pair(pair,record['events'],p)
                if sample_ready(record['pairs'],max_calls):record['trace_stop_reason']='sample-bound-drained';break
            record['pending']=[s['sequence'] for s in record['pairs'] if 'started' not in s['stages']]
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
            if not record['pending']:record['summary']=summarize(record['pairs'],record['events'],c)
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
            record['close_notes']=close_handles([getattr(remote,'sock',None),qstream,qs]);record['log_sha256']=sha(log_path.read_bytes()) if log_path.exists() else None
            json.dump(record,evidence,indent=2);evidence.write('\n')
    if error is not None:raise error
    require(record['exit_code']==0 and record['owned_process_closed'],'Owned process not closed')
    print('wrapper trace',record['trace_stop_reason'],'chains',len(record['pairs']),'pending',record['pending'],flush=True)
    return record


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--max-calls',type=int,default=24)
    p.add_argument('--guest-seconds',type=float,default=2);p.add_argument('--wall-seconds',type=int,default=180);a=p.parse_args();run(a.output,a.max_calls,a.guest_seconds,a.wall_seconds)
