"""r106 trace of the original post-MENU path, separate from functional acceptance."""
import argparse
import importlib.util
import json
from pathlib import Path
from unittest.mock import patch
import probe_z62_cw_preview_recovery as recovery
from z62_cw_reentry_observer import ReentryObserver,contract
from record_z62_action_evidence import workspace,digest,require


def run(qemu,card,group23,fixture,output,gdb,duration=24,wall_limit=600):
    qemu,output=map(workspace,(qemu,output));require(not output.exists(),'Use a new reentry directory')
    stream=recovery.parent.parent.parent.parent.finite.parent
    tracer=ReentryObserver(qemu);previous_snapshot=stream.original.snapshot
    previous_spec=importlib.util.spec_from_file_location;previous_cadence=stream.FrameCadence
    previous_plan=recovery.RecoveryPlan
    sources={str(Path(p).resolve()):digest(Path(p)) for p in (__file__,recovery.__file__,
        __import__('z62_cw_reentry_observer').__file__)}
    contract((recovery.parent.hardware.device.ROOT/'artifacts/z62-reference-1.70/master.bin').read_bytes())

    class Plan(previous_plan):
        def step(self,row):
            event=super().step(row)
            if event and event['action']=='half':
                tracer.half_ns=row['virtual_time_ns'];tracer.record['half_request_ns']=tracer.half_ns
            return event

    class Cadence(previous_cadence):
        def suggest(self,now,eligible=True):
            tracer.tick()
            if tracer.remote is not None and now>=int((duration-.2)*1e9):tracer.close('bounded-window-end')
            return super().suggest(now,eligible)

    def snapshot(machine,layout):
        tracer.tick();row=previous_snapshot(machine,layout);now=row['virtual_time_ns']
        app=machine._words(0xc1811e50,5)
        if app[4]&255==1 and not tracer.record['attached'] and not tracer.finished:
            tracer.attach(machine,layout);tracer.entered_menu=True
            tracer.record['attach_menu_time_ns']=now
        if tracer.remote is not None and tracer.half_ns is not None and app[4]&255==3 and now>tracer.half_ns:
            tracer.record['post_half_index3_ns']=now;tracer.close('actual-post-half-index3')
        row['independent_reentry_GDB_attached']=tracer.record['attached']
        row['functional_acceptance_eligible']=False
        return row

    def spec(name,*args,**kwargs):
        result=previous_spec(name,*args,**kwargs)
        if name=='z62_main_stream_host':
            delegate=result.loader
            class Loader:
                def create_module(self,spec):return delegate.create_module(spec)
                def exec_module(self,module):
                    delegate.exec_module(module);base=module.Z62Machine
                    class CleanupGuard(base):
                        def _cleanup(self):
                            if tracer.machine is self:tracer.close('before-owned-process-cleanup')
                            return super()._cleanup()
                    module.Z62Machine=CleanupGuard
            result.loader=Loader()
        return result

    try:
        with (patch.object(stream.original,'snapshot',snapshot),patch.object(stream,'FrameCadence',Cadence),
                patch.object(recovery,'RecoveryPlan',Plan),patch.object(importlib.util,'spec_from_file_location',spec)):
            result,prior=recovery.run(qemu,card,group23,fixture,output,gdb,duration,wall_limit)
    finally:
        if tracer.remote is not None:tracer.close('outer-finally')
    require(all(digest(Path(p))==sha for p,sha in sources.items()),'Reentry source changed')
    sources.update(tracer.record.get('source_sha256',{}))
    receipt={'schema':1,'version':'2026.11.04-CW-reentry-r106','result_sha256':digest(output/'result.json'),
        'recovery_observer_sha256':digest(output/'recovery-observer.json'),'source_sha256':sources,
        'trace':tracer.record,'completed_observation':result['completed_observation'],
        'process_exit_code':result.get('process_exit_code'),'actual_independent_guest_GDB_attached':tracer.record['attached'],
        'parent_flags_describe_only_their_builtin_observers':True,'functional_acceptance_eligible':False,
        'guest_memory_or_registers_written':False,'camera_accessed':False,'AF_modified':False,
        'scope':'Diagnostic only. Independent guest breakpoints perturb timing; parent no-debugger flags are not global acceptance claims.'}
    with (output/'reentry-observation.json').open('x',encoding='utf-8') as handle:json.dump(receipt,handle,ensure_ascii=False,indent=2)
    print(json.dumps({k:v for k,v in receipt.items() if k not in ('source_sha256','trace')}),flush=True)
    return result,receipt


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--qemu',type=Path,default=recovery.parent.hardware.DEFAULT_QEMU)
    for name in ('card','group23','fixture','output'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--gdb',type=Path,default=recovery.host_capture.DEFAULT_GDB)
    parser.add_argument('--duration',type=float,default=24);parser.add_argument('--wall-limit',type=float,default=600)
    args=parser.parse_args();result,receipt=run(args.qemu,args.card,args.group23,args.fixture,args.output,args.gdb,args.duration,args.wall_limit)
    raise SystemExit(0 if result['completed_observation'] and not result.get('failure') and result.get('process_exit_code')==0 else 1)
