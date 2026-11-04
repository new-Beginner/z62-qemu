"""r97 independent continuous MAIN source over the frozen r93/r95 platform.

Source scheduling follows the real virtual clock and actual device ownership.
Original timeouts, ready conditions, queues and firmware bytes remain intact.
"""
import argparse
from contextlib import ExitStack
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace
from unittest.mock import patch
import probe_z62_capturework_original as original
import probe_z62_group_parameter_input as input_driver
import run_z62_capture_group as hardware
import z62_workspace_paths as paths
import z62_original_clock_guard as clock
from z62_kernel_event_layout import contract
from z62_main_stream import FrameCadence,AuditedMailbox
from z62_live_ready_observer import ReadyObserver
from record_z62_action_evidence import workspace,digest,require

ROOT=Path(__file__).resolve().parents[1]
VERSION='2026.11.04-main-stream-r97c'


def run(qemu,card,group23,fixture,output,duration=8,wall_limit=300,observe=False,finite=False):
    qemu,card,group23,fixture,output=map(workspace,(qemu,card,group23,fixture,output))
    require(not output.exists() and 8<=duration<=30 and 30<=wall_limit<=600,'New bounded stream experiment required')
    build=hardware.verify_build(qemu);meta=json.loads(fixture.with_name(fixture.name+'.json').read_text(encoding='utf-8'))
    require(meta['mode']=='reference' and digest(fixture)==meta['output_sha256'] and not meta['factory_calibration'],
        'Explicit C-reference group input required')
    require(digest(group23)=='c7dd14358b45b2813fdee85fc587bcdd5899f7a81e0d5830513d631235bcc700','Reviewed synthetic group23 required')
    require(card.is_file() and card.suffix.lower() in ('.raw','.img') and card.stat().st_size%512==0,'Dedicated virtual card file required')
    output.mkdir(parents=True);source=AuditedMailbox(output/'main-source');cadence=FrameCadence()
    record={'schema':1,'version':VERSION,'completed_observation':False,'camera_accessed':False,
        'binary_sha256':build['binary_sha256'],'group_fixture_sha256':digest(fixture),
        'original_card_sha256':digest(card),'source_clock':'actual full 64-bit original counter',
        'nominal_source_fps':30,'source_epoch':source.epoch,'all_accepted_packets_reconstructable':True,
        'legacy_finite_model_explicitly_enabled':finite,
        'original_timeouts_or_queues_modified':False,'ready_or_completion_injected':False,
        'post_boot_software_memory_or_register_fixups':False,'publications':[],'samples':[]}
    tracked=[Path(__file__),Path(original.__file__),Path(input_driver.__file__),ROOT/'tools/z62_main_stream.py',
        ROOT/'tools/z62_live_ready_observer.py',Path(clock.__file__),Path(hardware.__file__)]
    record['source_sha256']={str(p):digest(p) for p in tracked}
    machine=process=staged=None;old_popen=subprocess.Popen;old_path=list(sys.path);observer=ReadyObserver(qemu) if observe else None
    journal=(output/'stream.jsonl').open('x',encoding='utf-8')
    def emit(kind,value):journal.write(json.dumps({'kind':kind,'value':value})+'\n');journal.flush()
    try:
        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ,{'Z62_PROJECT_ROOT':str(ROOT),'Z62_PROJECT_DRIVE':'Q:/',
                'TEMP':'Q:/.runtime/tmp','TMP':'Q:/.runtime/tmp','PI_SCRATCH_DIR':'Q:/.runtime/tmp','PYTHONDONTWRITEBYTECODE':'1'}))
            paths.ensure_alias();stack.enter_context(patch.object(original.reference,'Path',paths.WorkspacePath))
            staged,session=original.reference.stage('z62',paths.WorkspacePath(qemu),experimental_parameters=True,updates=True)
            tree=staged/'source';original.transaction.apply_console(tree);original.capcom.apply_status(tree)
            original.stream.apply_status(tree);original.shutter.apply_console(tree);original.lens.apply_console(tree)
            original.host_paths.apply_console(tree)
            record.update(session=str(staged),synthetic_parameters=session['parameters'],master_sha256=digest(staged/'inputs/master.bin'))
            require(record['master_sha256']==original.MASTER_SHA,'Original master differs')
            layout=contract((staged/'inputs/master.bin').read_bytes())
            original.reference.install_native_process_adapter(staged);native_popen=subprocess.Popen
            class StreamProcess(native_popen):
                def __init__(self,command,*args,**kwargs):
                    if isinstance(command,(list,tuple)) and Path(command[0]).name.lower()=='qemu-system-arm.exe':
                        command=input_driver.statistics.command_profile(list(command),paths.WorkspacePath(group23),True,True)
                        command+=['-global','nikon-z72-input-config.z62-capture-group=on',
                            '-device',f'loader,file={paths.WorkspacePath(fixture)},addr=0x132c0000,force-raw=on']
                        if finite:command+=['-global','nikon-z72-input-config.functional-finite-stats=on']
                        require(any('snapshot=on' in value for value in command),'Virtual card snapshot required')
                        record['effective_command']=list(command)
                    super().__init__(command,*args,**kwargs)
            subprocess.Popen=StreamProcess;sys.path.insert(0,str(tree))
            spec=importlib.util.spec_from_file_location('z62_main_stream_host',tree/'tools/z62_console.py')
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            args=SimpleNamespace(qemu=paths.WorkspacePath(qemu),master=staged/'inputs/master.bin',slave=staged/'inputs/slave.bin',
                controller=staged/'inputs/controller.bin',parameters=staged/'parameters',runs=staged/'runs',port=0,
                sd_card=paths.WorkspacePath(card),auto_menu=False,wsl=False,main_screen_experiment=False,sampling_source=False,
                input_trace=False,update_store=staged/'unused-update-store',update_image=None)
            machine=module.Z62Machine(args);require(machine.restart(),'Could not start own original stream session')
            remove=original.shutil.rmtree
            def preserve_before_remove(target,*args,**kwargs):
                physical=Path(target).resolve()
                require(physical.is_relative_to(ROOT),'Refusing cleanup outside the original experiment workspace')
                if machine.work and physical==Path(machine.work).resolve():
                    for name in ('command.json','console.txt'):
                        path=physical/name;destination=output/('closed-'+name)
                        if path.is_file() and not destination.exists():
                            with destination.open('xb') as handle:handle.write(path.read_bytes())
                return remove(target,*args,**kwargs)
            stack.enter_context(patch.object(original.shutil,'rmtree',preserve_before_remove))
            deadline=time.monotonic()+wall_limit;next_sample=0;report_at=0;qualified=False
            while time.monotonic()<deadline:
                if machine.phase=='failed':raise RuntimeError('Original start failed: '+str(machine.error))
                if machine.phase!='running':time.sleep(.05);continue
                with machine.io:
                    process=machine.process
                    if not qualified:record['clock_qualification']=clock.wait_for_clock(machine);qualified=True
                    if observer:observer.tick(machine,layout)
                    now=original.virtual_ns(*machine._key_clock())
                    cw=json.loads(machine.qmp.command('qom-get',{'path':'/machine/master-input','property':'capturework-status'}))
                    stats=json.loads(machine.qmp.command('qom-get',{'path':'/machine/master-input','property':'capturework-statistics-status'}))
                    group=json.loads(machine.qmp.command('qom-get',{'path':'/machine/master-input','property':'capture-group-status'}))
                    if now>=next_sample:
                        row=original.snapshot(machine,layout);row['capturework_statistics']=stats;row['capture_group']=group
                        row['legacy_RAW_accepted']=machine.qmp.command('qom-get',{'path':'/machine/master-input','property':'raw-accepted'})
                        row['finite_statistics']={prop:machine.qmp.command('qom-get',{'path':'/machine/master-input','property':prop})
                            for prop in ('functional-finite-stats','finite-frames','finite-batches','finite-rejected','finite-reason')}
                        row['finite_descriptor_words']=machine._words(0x2006a53c,6)
                        record['samples'].append(row);emit('sample',row);next_sample=now+100_000_000
                    eligible=not cw['active'] and not cw['pending_front'] and not cw['pending_raw'] and not stats['pending'] and not group['pending'] and cw['reason'] in ('source-missing-or-old','success')
                    proposal=cadence.suggest(now,eligible)
                    if proposal and now<duration*1_000_000_000:
                        width,height=original.main_geometry(machine._words(0x20069d00,2))
                        path,row=source.prepare(proposal,width,height,(proposal['frame']//30)%2)
                        machine.qmp.command('qom-set',{'path':'/machine/master-input','property':'capturework-main-file',
                            'value':str(paths.WorkspacePath(path))})
                        cadence.accept(proposal);record['publications'].append(row);emit('publication',row)
                    if time.monotonic()>=report_at:
                        print('MAIN_STREAM',now,cadence.publication,cw['completed'],group['completed'],stats['consumed'],flush=True)
                        report_at=time.monotonic()+15
                    if now>=duration*1_000_000_000:
                        record['completed_observation']=True;break
                time.sleep(.01)
            else:raise TimeoutError('Original main stream reached wall limit')
            with machine.io:
                if observer:observer.close()
                final=original.snapshot(machine,layout)
                for key,prop in (('capture_group','capture-group-status'),('capturework_statistics','capturework-statistics-status')):
                    final[key]=json.loads(machine.qmp.command('qom-get',{'path':'/machine/master-input','property':prop}))
                final['legacy_RAW_accepted']=machine.qmp.command('qom-get',{'path':'/machine/master-input','property':'raw-accepted'})
                record['final']=final;record['runtime_work']=str(machine.work)
                for name in ('command.json','console.txt'):
                    path=machine.work/name
                    if path.is_file():
                        with (output/name).open('xb') as handle:handle.write(path.read_bytes())
            with (output/'final-lcd.png').open('xb') as handle:handle.write(machine.frame_png())
            machine.close();record['process_exit_code']=process.poll()
    except Exception as exc:record['failure']={'type':type(exc).__name__,'message':str(exc)}
    finally:
        if observer:
            try:observer.close()
            except Exception as exc:record['observer_cleanup_failure']=str(exc)
            record['ready_observer']=observer.record
        if machine is not None and not machine.shutdown.is_set():
            if machine.work:
                for name in ('command.json','console.txt'):
                    path=machine.work/name
                    if path.is_file() and not (output/name).exists():
                        with (output/name).open('xb') as handle:handle.write(path.read_bytes())
            try:machine.close()
            except Exception as exc:record['cleanup_failure']=str(exc)
        if process is not None:record['process_exit_code']=process.poll()
        record['accepted_publications']=cadence.publication;record['source_frames_skipped']=cadence.skipped
        record['source_bytes_unchanged']=all(digest(Path(p))==sha for p,sha in record['source_sha256'].items())
        record['original_card_unchanged']=digest(card)==record['original_card_sha256']
        subprocess.Popen=old_popen;sys.path[:]=old_path;journal.close()
        with (output/'result.json').open('x',encoding='utf-8') as handle:json.dump(record,handle,ensure_ascii=False,indent=2)
    print(json.dumps({k:record.get(k) for k in ('completed_observation','failure','cleanup_failure','process_exit_code','accepted_publications','source_frames_skipped')},ensure_ascii=False),flush=True)
    return record


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--qemu',type=Path,default=hardware.DEFAULT_QEMU)
    parser.add_argument('--card',type=Path,required=True);parser.add_argument('--group23',type=Path,required=True)
    parser.add_argument('--fixture',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--duration',type=float,default=8);parser.add_argument('--wall-limit',type=float,default=300)
    parser.add_argument('--observe-ready',action='store_true');parser.add_argument('--legacy-finite',action='store_true');args=parser.parse_args()
    record=run(args.qemu,args.card,args.group23,args.fixture,args.output,args.duration,args.wall_limit,args.observe_ready,args.legacy_finite)
    raise SystemExit(0 if record['completed_observation'] and not record.get('failure') and record.get('process_exit_code')==0 else 1)
