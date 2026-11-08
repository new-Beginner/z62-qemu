"""r18 bounded read-only original registration/business BLX/return-loop observer."""
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
import business_contract as t
from startup_contract import ROOT,BASE,require,sha,read_inputs

OUTPUT=ROOT/'analysis/fenestra-z62-business-r18'
FALSE_FIELDS=tuple(sorted(set(old.FALSE_FIELDS+t.LIMITATIONS)))
SOURCES=tuple(sorted(set(old.SOURCES+('fenestra/z62/business_contract.py',
    'fenestra/z62/observe_business.py','fenestra/z62/verify_business.py'))))
model_identity=old.model_identity
command=old.command


def registers(remote,tid):
    remote.select_thread(int(tid,16));packet=remote.regs()
    return {n:remote.get(packet,n) for n in old.REGISTERS}


def run(output,minimum=8,guest_seconds=2,wall_seconds=240):
    output=output.resolve()
    require(output.is_relative_to(OUTPUT) and not output.exists() and not output.with_suffix('.qemu.log').exists(),'Use new r18 evidence output')
    require(type(minimum) is int and 8<=minimum<=32 and 1<=guest_seconds<=6 and 30<=wall_seconds<=300,'Invalid business bounds')
    identity=model_identity();c,images=t.collect(),read_inputs();buf=ctypes.create_unicode_buffer(32768)
    require(not ctypes.windll.kernel32.QueryDosDeviceW('Q:',buf,len(buf)),'Q: already occupied')
    require(not subprocess.check_output(['powershell.exe','-NoProfile','-Command',
        "Get-CimInstance Win32_Process -Filter \"name like 'qemu%'\" | Select-Object -ExpandProperty ProcessId"],encoding='utf-8').strip(),'Existing QEMU running')
    r=dict(schema=1,tool=t.TOOL,created_at=datetime.now(timezone.utc).isoformat(),completed=False,**identity,
        contract=c,firmware_inputs=c['inputs'],sources={n:sha((ROOT/n).read_bytes()) for n in SOURCES},
        firmware_loaded=True,reset_pc_initialized_by_qemu_loader=True,breakpoint_timing_perturbed=True,
        default_completion_logic_disabled=False,controller_link_enabled=False,
        owned_shutdown='QMP quit; NOT camera normal shutdown',minimum_returned_calls=minimum,
        guest_target_seconds=guest_seconds,wall_limit_seconds=wall_seconds,events=[],registrations=[],calls=[],pauses=[],
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
            for index in range(t.EVENT_CAP):
                remaining=wall_seconds-(time.monotonic()-start)
                if remaining<=0:r['trace_stop_reason']='wall-bound';break
                remote.sock.settimeout(min(15,remaining))
                try:stop=remote.command('c')
                except socket.timeout:
                    remote.sock.settimeout(15);stop=remote.interrupt()
                    r['pauses'].append(dict(phase='trace',stop=stop,ticks=old.ticks(remote)));r['trace_stop_reason']='quiet-bound';break
                remote.sock.settimeout(15);require(stop.startswith('T05'),'Unexpected business stop')
                previous=remote.command('qC');tid=old.stopped_thread(stop,previous);regs=registers(remote,tid);pc=regs['pc']
                head=remote.read(BASE,0x6C);roles=[role for role,img in images.items() if head==img[:0x6C]]
                require(len(roles)==1 and pc in active,'Unknown original role/breakpoint')
                role=roles[0];p=c['roles'][role];local=(int(tid,16)-1)%2
                row=dict(sequence=index,role=role,thread=tid,local_cpu=local,stop=stop,previous_selected_thread=previous,
                    registers=regs,image_head=head.hex(),rom_window=dict(address=pc-16,bytes=remote.read(pc-16,32).hex()),
                    system={n:remote.read_register(n) for n in old.SYSTEM},model_ticks=old.selected_ticks(remote,tid),
                    current=list(struct.unpack('<2I',remote.read(p['context']['current'],8))))
                d,phase,pi=t.classify(r['registrations'],r['calls'],row,p);row.update(phase=phase,kind=d['kind'],pair_index=pi,memory={})
                if phase=='register':require(len(r['registrations'])<t.CAP,'Registration bound exceeded')
                if phase=='call':require(len(r['calls'])<t.CAP,'Business call bound exceeded')
                for label,address,size in t.read_plan(r['registrations'],r['calls'],row,p):
                    require(t.bounded_read(p,address,size),'Unbounded business read: '+label)
                    row['memory'][label]=remote.read(address,size).hex()
                remote.select_thread(int(tid,16));row['step_reply']=old.advance_isolated(remote,pc,tid,True)
                row['after_registers']=registers(remote,tid)
                row['after_system']={n:remote.read_register(n) for n in old.SYSTEM}
                if phase=='register':
                    address=row['after_registers']['sp'];require(t.bounded_stack(p,address,24),'Unbounded actual setter PUSH')
                    row['after_stack']=remote.read(address,24).hex()
                elif phase=='store':row['after_object']=remote.read(regs['r4'],48).hex()
                elif phase=='call':
                    target=row['after_registers']['pc']
                    require(BASE+16<=target and target+16<=BASE+len(images[role])-2,'Business target outside original ROM')
                    row['target_rom']=dict(address=target,bytes=remote.read(target,16).hex())
                    row['target_current']=list(struct.unpack('<2I',remote.read(p['context']['current'],8)))
                    row['target_system']={n:remote.read_register(n) for n in old.SYSTEM}
                t.ingest(r['registrations'],r['calls'],row,p);r['events'].append(row)
                if t.ready(r['registrations'],r['calls'],minimum):r['trace_stop_reason']='sample-bound-drained';break
            r['pending_registrations']=[s['sequence'] for s in r['registrations'] if s['stored'] is None]
            r['pending_calls']=[s['sequence'] for s in r['calls'] if s['returned'] is None]
            for pc in sorted(active):remote.breakpoint(pc,False)
            r['trace_end_ticks']=old.ticks(remote)
            while old.ticks(remote)<guest_seconds*48000000:
                remaining=wall_seconds-(time.monotonic()-start)
                if remaining<=0:break
                remote.sock.settimeout(min(15,remaining))
                try:stop=remote.command('c')
                except socket.timeout:remote.sock.settimeout(15);stop=remote.interrupt()
                remote.sock.settimeout(15);require(stop.startswith('T02'),'Unexpected untraced stop')
                r['pauses'].append(dict(phase='untraced',stop=stop,ticks=old.ticks(remote)))
            r['final_ticks']=old.ticks(remote);r['guest_target_reached']=r['final_ticks']>=guest_seconds*48000000
            r['final_cpus']=old.sample(remote,images);r['final_status']=session.query('query-status')
            r['summary']=t.summarize(r['registrations'],r['calls'])
            r['wall_seconds']=time.monotonic()-start;r['completed']=True
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
    print(r['trace_stop_reason'],'registrations',len(r['registrations']),'calls',len(r['calls']),flush=True)
    return r


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--minimum',type=int,default=8);ap.add_argument('--guest-seconds',type=float,default=2)
    ap.add_argument('--wall-seconds',type=int,default=240);a=ap.parse_args();run(a.output,a.minimum,a.guest_seconds,a.wall_seconds)
