"""r19 read-only bounded natural queue callback observation; no firmware repair."""
import argparse
import ctypes
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import time
import observe_task_launch as old
from observe_business import registers
import queue_contract as t
from startup_contract import ROOT,BASE,require,sha,read_inputs

OUTPUT=ROOT/'analysis/fenestra-z62-queue-r19'
FALSE_FIELDS=tuple(sorted(set(old.FALSE_FIELDS+t.LIMITATIONS)))
SOURCES=tuple(sorted(set(old.SOURCES+('fenestra/z62/business_contract.py','fenestra/z62/observe_business.py',
    'fenestra/z62/queue_contract.py','fenestra/z62/observe_queue.py','fenestra/z62/verify_queue.py'))))
model_identity=old.model_identity
command=old.command


def run(output,guest_seconds=2,wall_seconds=240):
    output=output.resolve()
    require(output.is_relative_to(OUTPUT) and not output.exists() and not output.with_suffix('.qemu.log').exists(),'Use new r19 output')
    require(guest_seconds in (2,3) and wall_seconds==240,'Fixed r19 horizon/bounds differ')
    identity=model_identity();c,images=t.collect(),read_inputs();buf=ctypes.create_unicode_buffer(32768)
    require(not ctypes.windll.kernel32.QueryDosDeviceW('Q:',buf,len(buf)),'Q: already occupied')
    require(not subprocess.check_output(['powershell.exe','-NoProfile','-Command',
        "Get-CimInstance Win32_Process -Filter \"name like 'qemu%'\" | Select-Object -ExpandProperty ProcessId"],encoding='utf-8').strip(),'Existing QEMU running')
    r=dict(schema=1,tool=t.TOOL,created_at=datetime.now(timezone.utc).isoformat(),completed=False,**identity,
        contract=c,firmware_inputs=c['inputs'],sources={n:sha((ROOT/n).read_bytes()) for n in SOURCES},
        firmware_loaded=True,reset_pc_initialized_by_qemu_loader=True,breakpoint_timing_perturbed=True,
        default_completion_logic_disabled=False,controller_link_enabled=False,
        owned_shutdown='QMP quit; NOT camera normal shutdown',registration_observed=False,
        guest_target_seconds=guest_seconds,wall_limit_seconds=wall_seconds,events=[],calls=[],pauses=[],
        **{n:False for n in FALSE_FIELDS})
    process=remote=session=sock=stream=None;error=row=None;own_alias=False;active=t.points(c)
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf-8') as evidence:
        try:
            subprocess.run(['subst.exe','Q:',str(ROOT)],check=True);own_alias=True
            require(Path('Q:/').samefile(ROOT),'Workspace alias differs')
            ports=old.free_port(),old.free_port();require(ports[0]!=ports[1],'Port collision')
            r['command']=cmd=command(ports)
            env=dict(os.environ,TEMP=os.environ['PI_SCRATCH_DIR'],TMP=os.environ['PI_SCRATCH_DIR'],TMPDIR=os.environ['PI_SCRATCH_DIR'],PYTHONDONTWRITEBYTECODE='1')
            with output.with_suffix('.qemu.log').open('xb') as log:
                process=subprocess.Popen(cmd,stdout=subprocess.DEVNULL,stderr=log,env=env)
            r['owned_pid']=process.pid;sock=old.connect(ports[1],process);sock.settimeout(15)
            stream=sock.makefile('rwb');json.loads(stream.readline());session=old.BootSession();session.qmp=stream
            session.query('qmp_capabilities');remote=old.BootRemote(ports[0])
            r['model_tree']=session.query('human-monitor-command',{'command-line':'info qtree'})
            for pc in sorted(active):remote.breakpoint(pc)
            start=time.monotonic();r['trace_stop_reason']='event-bound'
            while len(r['events'])<t.EVENT_CAP:
                remaining=wall_seconds-(time.monotonic()-start)
                require(remaining>0,'Queue wall bound exceeded');remote.sock.settimeout(min(15,remaining))
                try:stop=remote.command('c')
                except socket.timeout:
                    remote.sock.settimeout(15);stop=remote.interrupt();ticks=old.ticks(remote)
                    r['pauses'].append(dict(after_events=len(r['events']),stop=stop,ticks=ticks))
                    if ticks>=guest_seconds*48000000:r['trace_stop_reason']='model-horizon';break
                    continue
                remote.sock.settimeout(15);require(stop.startswith('T05'),'Unexpected queue stop')
                previous=remote.command('qC');tid=old.stopped_thread(stop,previous);regs=registers(remote,tid);pc=regs['pc']
                head=remote.read(BASE,0x6c);roles=[role for role,img in images.items() if head==img[:0x6c]]
                require(len(roles)==1 and pc in active,'Unknown original queue role/point')
                role=roles[0];p=c['roles'][role];local=(int(tid,16)-1)%2
                row=dict(sequence=len(r['events']),role=role,thread=tid,local_cpu=local,stop=stop,previous_selected_thread=previous,
                    registers=regs,image_head=head.hex(),rom_window=dict(address=pc-16,bytes=remote.read(pc-16,32).hex()),
                    system={n:remote.read_register(n) for n in old.SYSTEM},model_ticks=old.selected_ticks(remote,tid),
                    current=list(struct.unpack('<2I',remote.read(p['context']['current'],8))))
                phase,pi=t.classify(r['calls'],row,p);row.update(phase=phase,pair_index=pi,memory={})
                require(phase!='call' or len(r['calls'])<t.CAP,'Outer queue call bound exceeded')
                require(phase!='store' or sum(len(s['stores']) for s in r['calls'])<t.STORE_CAP,'Queue store bound exceeded')
                for label,address,size in t.read_plan(r['calls'],row,p):
                    require(t.bounded_read(p,address,size),'Unbounded queue read: '+label)
                    row['memory'][label]=remote.read(address,size).hex()
                remote.select_thread(int(tid,16));row['step_reply']=old.advance_isolated(remote,pc,tid,True)
                row['after_registers']=registers(remote,tid);row['after_system']={n:remote.read_register(n) for n in old.SYSTEM}
                if phase=='entry':
                    address=row['after_registers']['sp'];require(t.bounded_stack(p,address,24),'Unbounded queue PUSH')
                    row['after_stack']=remote.read(address,24).hex()
                elif phase=='store':row['after_indices']=remote.read(regs['r4'],8).hex()
                if phase in ('call','nested'):
                    target=row['after_registers']['pc'];require(BASE+16<=target and target+16<=BASE+len(images[role])-2,'Queue target outside original ROM')
                    row['target_rom']=dict(address=target,bytes=remote.read(target,16).hex())
                    row['target_current']=list(struct.unpack('<2I',remote.read(p['context']['current'],8)))
                    row['target_system']={n:remote.read_register(n) for n in old.SYSTEM}
                t.ingest(r['calls'],row,p);r['events'].append(row)
            require(r['trace_stop_reason']=='model-horizon','Queue event bound exceeded')
            for pc in sorted(active):remote.breakpoint(pc,False)
            r['final_ticks']=old.ticks(remote);r['guest_target_reached']=r['final_ticks']>=guest_seconds*48000000
            r['final_cpus']=old.sample(remote,images);r['final_status']=session.query('query-status')
            r['summary']=t.local_summary(r['calls']);r['wall_seconds']=time.monotonic()-start;r['completed']=True
        except Exception as exc:
            error=exc;r['failure']=type(exc).__name__+': '+str(exc)
            if row is not None:r['failure_event']=row
        finally:
            try:
                if process is not None and process.poll() is None and session is not None:r['quit_receipt']=old.quit_owned(session,process)
            except Exception as exc:r['quit_failure']=type(exc).__name__+': '+str(exc)
            finally:
                if process is not None and process.poll() is None:
                    process.terminate()
                    try:process.wait(timeout=10)
                    except subprocess.TimeoutExpired:process.kill();process.wait(timeout=10)
                    r['forced_host_cleanup']=True
                r['exit_code']=None if process is None else process.returncode;r['owned_process_closed']=process is not None and process.poll() is not None
                r['rsp_commands']=getattr(remote,'audit',[]);r['rsp_controls']=getattr(remote,'controls',[]);r['qmp_commands']=getattr(session,'audit',[])
                r['close_notes']=old.close_handles([getattr(remote,'sock',None),stream,sock])
                if own_alias:
                    require(Path('Q:/').samefile(ROOT),'Owned alias changed');subprocess.run(['subst.exe','Q:','/D'],check=True)
                r['mapping_removed']=not bool(ctypes.windll.kernel32.QueryDosDeviceW('Q:',buf,len(buf)))
                log=output.with_suffix('.qemu.log');r['log_sha256']=sha(log.read_bytes()) if log.exists() else None
                json.dump(r,evidence,indent=2);evidence.write('\n')
    if error is not None:raise error
    print(json.dumps(r['summary'],indent=2),flush=True)
    return r


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--guest-seconds',type=int,choices=(2,3),default=2);a=ap.parse_args();run(a.output,a.guest_seconds)
