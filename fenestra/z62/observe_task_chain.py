"""r17 bounded read-only same-process create/launch/BX/first-instruction observer."""
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
import observe_task_joint as prior
import task_chain_contract as t
from startup_contract import ROOT,BASE,require,sha,read_inputs

old=prior.old
OUTPUT=ROOT/'analysis/fenestra-z62-task-chain-r17'
FALSE_FIELDS=tuple(sorted(set(prior.FALSE_FIELDS+t.LIMITATIONS)))
SOURCES=tuple(sorted(set(prior.SOURCES+('fenestra/z62/task_callback_contract.py',
    'fenestra/z62/task_chain_contract.py','fenestra/z62/observe_task_chain.py','fenestra/z62/verify_task_chain.py'))))
model_identity=prior.model_identity
command=prior.command
permanent_points=prior.permanent_points


def registers(remote,tid):
    remote.select_thread(int(tid,16));packet=remote.regs()
    return {n:remote.get(packet,n) for n in old.REGISTERS}


def plain_step(remote,tid):
    remote.select_thread(int(tid,16));reply=remote.command('vCont;s:'+tid)
    require(reply.startswith('T05') and old.stopped_thread(reply,remote.command('qC'))==tid,'Callback step CPU differs')
    return reply


def run(output,minimum=8,guest_seconds=2,wall_seconds=240):
    output=output.resolve()
    require(output.is_relative_to(OUTPUT) and not output.exists() and not output.with_suffix('.qemu.log').exists(),'Use new r17 evidence output')
    require(type(minimum) is int and 8<=minimum<=32 and 1<=guest_seconds<=6 and 30<=wall_seconds<=300,'Invalid chain bounds')
    identity=model_identity();c,images=t.collect(),read_inputs();buf=ctypes.create_unicode_buffer(32768)
    require(not ctypes.windll.kernel32.QueryDosDeviceW('Q:',buf,len(buf)),'Q: already occupied')
    require(not subprocess.check_output(['powershell.exe','-NoProfile','-Command',
        "Get-CimInstance Win32_Process -Filter \"name like 'qemu%'\" | Select-Object -ExpandProperty ProcessId"],encoding='utf-8').strip(),'Existing QEMU running')
    r=dict(schema=1,tool=t.TOOL,created_at=datetime.now(timezone.utc).isoformat(),completed=False,**identity,
        contract=c,firmware_inputs=c['inputs'],sources={n:sha((ROOT/n).read_bytes()) for n in SOURCES},
        firmware_loaded=True,reset_pc_initialized_by_qemu_loader=True,breakpoint_timing_perturbed=True,
        default_completion_logic_disabled=False,controller_link_enabled=False,
        owned_shutdown='QMP quit; NOT camera normal shutdown',minimum_joint_chains=minimum,
        guest_target_seconds=guest_seconds,wall_limit_seconds=wall_seconds,events=[],pairs=[],creations=[],pauses=[],
        **{n:False for n in FALSE_FIELDS})
    process=remote=session=sock=stream=None;error=row=None;own_alias=False;active=permanent_points(c)
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
                remote.sock.settimeout(15);require(stop.startswith('T05'),'Unexpected chain stop')
                previous=remote.command('qC');tid=old.stopped_thread(stop,previous);regs=registers(remote,tid);pc=regs['pc']
                head=remote.read(BASE,0x6C);roles=[role for role,img in images.items() if head==img[:0x6C]]
                require(len(roles)==1 and pc in active,'Unknown original role/breakpoint')
                role=roles[0];p=c['roles'][role];local=(int(tid,16)-1)%2
                row=dict(sequence=index,role=role,thread=tid,local_cpu=local,stop=stop,previous_selected_thread=previous,
                    registers=regs,image_head=head.hex(),rom_window=dict(address=pc-16,bytes=remote.read(pc-16,32).hex()),
                    system={n:remote.read_register(n) for n in old.SYSTEM},model_ticks=old.selected_ticks(remote,tid),
                    current=list(struct.unpack('<2I',remote.read(p['context']['current'],8))))
                phase,pi=t.classify(r['creations'],r['pairs'],row,p);row.update(phase=phase,pair_index=pi)
                if phase.startswith('create_') or phase in ('unmatched-construct','unmatched-initialized','word08_store','unmatched-update'):
                    row['memory']={}
                    if phase=='create_input':require(len(r['creations'])<t.CAP,'Creation bound exceeded')
                    for label,address,size in t.create_plan(r['creations'],row,p):
                        require(t.bounded_read(p,address,size),'Unbounded create read: '+label)
                        row['memory'][label]=remote.read(address,size).hex()
                elif phase=='input':
                    require(len(r['pairs'])<t.CAP,'Launch bound exceeded')
                    row['table_words']=list(struct.unpack('<2I',remote.read(p['table_global'],8)));base,count=row['table_words'];idx=regs['r0']&0xFFFF
                    require(0<idx<=count<=65535,'Outside table sample');tb=base+(idx-1)*216
                    require(t.bounded_ram(p['context'],tb,216),'Unbounded input TCB')
                    row.update(tcb_address=tb,tcb=remote.read(tb,216).hex());t.launch.check_input(row,p)
                    row['creation_index']=t.creation_for_input(r['creations'],row)
                    if row['creation_index'] is not None:
                        address=r['creations'][row['creation_index']]['analysis']['object_address']
                        require(t.bounded_read(p,address,32),'Unbounded launch object');row['launch_object']=remote.read(address,32).hex()
                elif phase=='prepared':
                    tb,fp=regs['r4'],regs['r0']
                    require(t.bounded_ram(p['context'],tb,216) and t.bounded_ram(p['context'],fp,76),'Unbounded publish')
                    row.update(tcb_address=tb,tcb=remote.read(tb,216).hex(),frame_address=fp,frame=remote.read(fp,76).hex())
                    require(t.launch.bounded_stack(p,regs['sp'],40),'Unbounded saved stack');row['saved_stack']=remote.read(regs['sp'],40).hex()
                    entry=t.launch.check_prepared(row,p)['entry_pc'];require(entry not in permanent_points(c),'Entry/permanent conflict')
                    if entry not in active:remote.breakpoint(entry);active.add(entry)
                elif phase=='returned':
                    require(t.launch.bounded_stack(p,regs['sp'],40),'Unbounded return stack');row['saved_stack']=remote.read(regs['sp'],40).hex()
                elif phase=='entered':
                    tb=row['current'][local];require(t.bounded_ram(p['context'],tb,216),'Unbounded entry TCB')
                    row.update(tcb_address=tb,tcb=remote.read(tb,216).hex());ci=r['pairs'][pi]['input'].get('creation_index')
                    if ci is not None:
                        address=r['creations'][ci]['analysis']['object_address'];require(t.bounded_read(p,address,32),'Unbounded entry object')
                        row['launch_object']=remote.read(address,32).hex()
                    if regs['cpsr']&32:
                        require(pc==p['shared_entry'] and t.bounded_read(p,regs['r1'],8),'Unbounded shared descriptor')
                        row['callback']=dict(descriptor_address=regs['r1'],descriptor=remote.read(regs['r1'],8).hex())
                remote.select_thread(int(tid,16));row['step_reply']=old.advance_isolated(remote,pc,tid,True)
                row['after_registers']=registers(remote,tid)
                row['after_system']={n:remote.read_register(n) for n in old.SYSTEM}
                if phase in ('input','create_input'):
                    size=40 if phase=='input' else 48;address=row['after_registers']['sp']
                    require(t.launch.bounded_stack(p,address,size),'Unbounded actual PUSH');row['after_stack']=remote.read(address,size).hex()
                if phase in ('word08_store','unmatched-update'):row['updated_object_after']=remote.read(regs['r5'],32).hex()
                if phase=='returned':
                    target=row['after_registers']['pc'];require(BASE+16<=target<BASE+len(images[role])-18,'Return outside ROM')
                    row['return_rom']=dict(address=target-16,bytes=remote.read(target-16,32).hex())
                if 'callback' in row:
                    cb=row['callback'];field=struct.unpack('<2I',bytes.fromhex(cb['descriptor']))[1]
                    require(row['after_registers']==dict(regs,pc=pc+2,r1=field),'Independent LDR field differs')
                    expected_bx=t.bx_effect(row['after_registers']);target=expected_bx['pc']
                    require(BASE+16<=target and target+16<=BASE+len(images[role])-2,'Unbounded callback ROM')
                    cb['bx_reply']=plain_step(remote,tid);cb['after_bx']=registers(remote,tid)
                    require(cb['after_bx']==expected_bx,'Actual BX target differs')
                    cb['target_rom']=dict(address=target,bytes=remote.read(target,16).hex())
                    require(cb['target_rom']['bytes']==images[role][target-BASE:target-BASE+16].hex(),'Original callback ROM differs')
                    cb['target_current']=list(struct.unpack('<2I',remote.read(p['context']['current'],8)))
                    cb['target_system']={n:remote.read_register(n) for n in old.SYSTEM}
                    expected,stack,kind=t.first_effect(cb['after_bx'],bytes.fromhex(cb['target_rom']['bytes']))
                    if stack:require(t.bounded_read(p,stack['address'],len(bytes.fromhex(stack['bytes']))),'Unbounded callback PUSH')
                    cb['target_step_reply']=plain_step(remote,tid);cb['after_target']=registers(remote,tid)
                    cb['stack_write']=None if stack is None else dict(address=stack['address'],bytes=remote.read(stack['address'],len(bytes.fromhex(stack['bytes']))).hex())
                    cb['after_system']={n:remote.read_register(n) for n in old.SYSTEM}
                    row['callback_analysis']=t.check_callback(row,p,None if ci is None else r['creations'][ci]['analysis'])
                t.ingest(r['creations'],r['pairs'],row,p);r['events'].append(row)
                if phase=='entered' and pc not in old.entry_points(r['pairs'],c):remote.breakpoint(pc,False);active.remove(pc)
                if t.ready(r['creations'],r['pairs'],minimum):r['trace_stop_reason']='sample-bound-drained';break
            r['pending_creations']=[s['sequence'] for s in r['creations'] if s['initialized'] is None]
            r['pending']=[s['sequence'] for s in r['pairs'] if not t.launch.complete(s)]
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
            if not r['pending'] and not r['pending_creations']:r['summary']=t.summarize(r['creations'],r['pairs'])
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
    print(r['trace_stop_reason'],'creations',len(r['creations']),'launches',len(r['pairs']),'joint',len(t.links(r['creations'],r['pairs'])),flush=True)
    return r


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--minimum',type=int,default=8);ap.add_argument('--guest-seconds',type=float,default=2)
    ap.add_argument('--wall-seconds',type=int,default=240);a=ap.parse_args();run(a.output,a.minimum,a.guest_seconds,a.wall_seconds)
