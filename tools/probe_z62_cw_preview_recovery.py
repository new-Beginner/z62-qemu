"""r105 state-driven two-cycle observation on frozen r104, with owned fault capture."""
import argparse
from collections import deque
from contextlib import ExitStack
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import traceback
from unittest.mock import patch

import probe_z62_capturework_preview_original as parent
import z62_host_timeout_capture as host_capture
from z62_cw_preview_recovery import RecoveryPlan,VERSION
from z62_development_status import firmware_health
from record_z62_action_evidence import workspace,digest,require


def run(qemu,card,group23,fixture,output,gdb,duration=30,wall_limit=600):
    qemu,output=map(workspace,(qemu,output));require(not output.exists(),'Use a new recovery directory')
    build=parent.hardware.verify_build(qemu);gdb=Path(gdb).resolve(strict=True)
    stream=parent.parent.parent.parent.finite.parent;plan=RecoveryPlan()
    previous_snapshot=stream.original.snapshot;previous_spec=importlib.util.spec_from_file_location
    previous_install=stream.original.reference.install_native_process_adapter
    previous_read=stream.original.read_physical
    sources={str(Path(p).resolve()):digest(Path(p)) for p in (__file__,parent.__file__,
        host_capture.__file__,__import__('z62_cw_preview_recovery').__file__)}
    operations=deque(maxlen=64);faults=[];captures=[];launches=[];owner={};totals={'commands':0}
    output.parent.mkdir(parents=True,exist_ok=True)

    def save_capture(machine,label,row):
        ppm=output/(label+'.ppm');png=output/(label+'.png')
        machine.qmp.command('screendump',{'filename':str(stream.paths.WorkspacePath(ppm))})
        encoded=machine.frame_png.__func__.__globals__['ppm_to_png'](ppm.read_bytes())
        with png.open('xb') as handle:handle.write(encoded)
        captures.append({'label':label,'virtual_time_ns':row['virtual_time_ns'],'path':png.name,
            'sha256':digest(png),'application':row['application'],'source':row['CW_preview_source'],
            'preview_batches':row['other_pipeline_counters']['preview-batches']})

    def fault(machine,operation,exc):
        if faults:return
        folder=output/'first-host-timeout';folder.mkdir(parents=True,exist_ok=False)
        record={'operation':operation,'exception':{'type':type(exc).__name__,'message':str(exc)},
            'python_traceback':traceback.format_exc(),'thread':threading.current_thread().name,
            'python_thread_stacks':{str(tid):''.join(traceback.format_stack(frame)) for tid,frame in sys._current_frames().items()},
            'recent_operations':list(operations),'last_virtual_ns':owner.get('last_virtual_ns'),
            'machine_phase':machine.phase,'replayed':False,'host_capture_attempted':True,
            'camera_accessed':False,'firmware_written':False}
        faults.append(record)
        with (folder/'trigger.json').open('x',encoding='utf-8') as handle:json.dump(record,handle,ensure_ascii=False,indent=2)
        try:
            process=machine.process
            record['capture']=host_capture.capture(process,process.pid,actual_binary,build['binary_sha256'],
                folder/'host',gdb=gdb,console=machine.work/'console.txt')
        except Exception as error:record['capture_failure']={'type':type(error).__name__,'message':str(error)}
        with (folder/'result.json').open('x',encoding='utf-8') as handle:json.dump(record,handle,ensure_ascii=False,indent=2)
        print('RECOVERY_HOST_FAULT',json.dumps({k:record.get(k) for k in ('operation','last_virtual_ns','capture_failure')}),flush=True)

    def instrument(module):
        base=module.Z62Machine
        class ObservedMachine(base):
            def _start(self):
                owner['machine']=self;native_client=module.shared.QmpClient;machine=self
                class ObservedQmp(native_client):
                    def command(self,name,arguments=None,*args,**kwargs):
                        totals['commands']+=1
                        op={'sequence':totals['commands'],'command':name,'arguments':arguments,
                            'host_monotonic':time.monotonic(),'thread':threading.current_thread().name,'completed':False}
                        operations.append(op)
                        try:
                            result=super().command(name,arguments,*args,**kwargs);op['completed']=True;return result
                        except TimeoutError as exc:fault(machine,op,exc);raise
                with patch.object(module.shared,'QmpClient',ObservedQmp):super()._start()
            def _qtest(self,line):
                try:return super()._qtest(line)
                except TimeoutError as exc:fault(self,{'qtest':line},exc);raise
        module.Z62Machine=ObservedMachine

    def spec(name,*args,**kwargs):
        result=previous_spec(name,*args,**kwargs)
        if name=='z62_main_stream_host':
            delegate=result.loader
            class Loader:
                def create_module(self,spec):return delegate.create_module(spec)
                def exec_module(self,module):delegate.exec_module(module);instrument(module)
            result.loader=Loader()
        return result

    def install(work):
        result=previous_install(work);native=subprocess.Popen
        class AsciiProcess(native):
            def __init__(self,command,*args,**kwargs):
                command=list(command);owned=Path(command[0]).resolve()==qemu.resolve()
                if owned:command[0]=str(actual_binary)
                super().__init__(command,*args,**kwargs)
                if owned:launches.append({'pid':self.pid,'actual_command':list(self.args)})
        subprocess.Popen=AsciiProcess;return result

    def read(machine,*args,**kwargs):
        try:return previous_read(machine,*args,**kwargs)
        except TimeoutError as exc:fault(machine,{'qtest_physical_read':list(args)},exc);raise

    def snapshot(machine,layout):
        row=previous_snapshot(machine,layout);owner['last_virtual_ns']=row['virtual_time_ns']
        row.update(firmware_health(machine))
        row['CW_cohort']=json.loads(machine.qmp.command('qom-get',{
            'path':'/machine/master-input','property':'capturework-cohort-status'}))
        row['CW_preview_source']=json.loads(machine.qmp.command('qom-get',{
            'path':machine.capturework_boot_path,'property':'capturework-preview-status'}))
        words=machine._words(0xc1811e50,5)
        row['application']={'ready_word':words[0],'index':words[4]&255,'queued_keys':sorted(machine.key_events),
            'held':sorted(machine.held),'switch_words':machine._words(0xc25d6fc0,3)}
        event=plan.step(row);row['recovery_phase']=plan.phase;row['recovery_cycles']=plan.completed
        if event:
            if event['action'] in ('menu','half'):
                pin=event['pin'];machine._set_key_locked(pin,0);machine._set_key_locked(pin,1)
                event['electrical_press_release_queued']=True
            save_capture(machine,event['action']+'-'+str(event['cycle']),row)
            with (output/('event-%02d.json'%len(plan.events))).open('x',encoding='utf-8') as handle:json.dump(event,handle,ensure_ascii=False,indent=2)
            print('RECOVERY_EVENT',json.dumps({k:event[k] for k in ('action','cycle','virtual_time_ns','preview_batches','phase_after')}),flush=True)
        return row

    with ExitStack() as stack:
        stack.enter_context(patch.dict(os.environ,{'TEMP':'Q:/.runtime/tmp','TMP':'Q:/.runtime/tmp'}))
        stream.paths.ensure_alias()
        stack.enter_context(patch.object(host_capture,'Path',stream.paths.WorkspacePath))
        staged=stack.enter_context(host_capture.ascii_runtime(qemu,build['binary_sha256']));actual_binary=staged['binary']
        stack.enter_context(patch.object(importlib.util,'spec_from_file_location',spec))
        stack.enter_context(patch.object(stream.original.reference,'install_native_process_adapter',install))
        stack.enter_context(patch.object(stream.original,'read_physical',read))
        stack.enter_context(patch.object(stream.original,'snapshot',snapshot))
        result,prior=parent.run(qemu,card,group23,fixture,output,duration,wall_limit)
    require(all(digest(Path(p))==sha for p,sha in sources.items()),'Recovery observer source changed')
    record={'schema':1,'version':VERSION,'result_sha256':digest(output/'result.json'),
        'binary_sha256':build['binary_sha256'],'source_sha256':sources,'events':plan.events,'LCD_captures':captures,
        'completed_cycles':plan.completed,'phase':plan.phase,'host_faults':faults,'launches':launches,
        'ascii_runtime_file_sha256':staged['file_sha256'],'total_QMP_commands':totals['commands'],
        'functional_acceptance_eligible':not faults,'completed_observation':result['completed_observation'],
        'two_state_driven_cycles_observed':plan.completed==2,'preview_resume_verified':False,
        'camera_accessed':False,'firmware_modified':False,'control_commands_replayed':False,
        'acceptance_note':'Requires independent pixel/source evidence; two cycles or exit0 alone are insufficient.'}
    with (output/'recovery-observer.json').open('x',encoding='utf-8') as handle:json.dump(record,handle,ensure_ascii=False,indent=2)
    print(json.dumps({k:record[k] for k in ('completed_observation','completed_cycles','phase','functional_acceptance_eligible')}),flush=True)
    return result,record


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--qemu',type=Path,default=parent.hardware.DEFAULT_QEMU)
    for name in ('card','group23','fixture','output'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--gdb',type=Path,default=host_capture.DEFAULT_GDB)
    parser.add_argument('--duration',type=float,default=30);parser.add_argument('--wall-limit',type=float,default=600)
    args=parser.parse_args();result,receipt=run(args.qemu,args.card,args.group23,args.fixture,args.output,args.gdb,args.duration,args.wall_limit)
    raise SystemExit(0 if result['completed_observation'] and not result.get('failure') and result.get('process_exit_code')==0 else 1)
