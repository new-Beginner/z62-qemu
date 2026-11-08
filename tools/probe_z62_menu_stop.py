"""r111 capture real pre-MENU shutdown returns; never force capture rearm."""
import argparse
import json
from pathlib import Path
from unittest.mock import patch
import probe_z62_cw_app_transition as parent
import z62_cw_app_transition_observer as old
import z62_menu_stop_observer as current
from record_z62_action_evidence import workspace,digest,require


def run(qemu,card,group23,fixture,output,gdb,duration=24,wall_limit=600):
    output=workspace(output);stream=parent.parent.recovery.parent.parent.parent.parent.finite.parent
    previous=stream.original.snapshot
    sources={str(Path(p).resolve()):digest(Path(p)) for p in (__file__,parent.__file__,current.__file__,
        __import__('z62_stop_wait_observer').__file__)}
    def snapshot(machine,layout):
        row=previous(machine,layout);tracer=current.MenuStopObserver.last_created
        if (tracer is not None and not tracer.record['attached'] and not tracer.finished and
                row['virtual_time_ns']>=7_900_000_000 and row['other_pipeline_counters']['preview-batches']>0):
            app=machine._words(0xc1811e50,5)
            require(app[4]&255==3 and not machine.held and not machine.key_events,'Pre-MENU attach is not at an idle original preview')
            tracer.attach(machine,layout);tracer.record['attach_preview_time_ns']=row['virtual_time_ns']
            tracer.record['attached_before_first_MENU_requested']=True
        return row
    with (patch.object(old,'AppTransitionObserver',current.MenuStopObserver),patch.object(old,'POINTS',current.POINTS),
            patch.object(old,'contract',current.contract),patch.object(stream.original,'snapshot',snapshot)):
        result,prior=parent.run(qemu,card,group23,fixture,output,gdb,duration,wall_limit)
    require(all(digest(Path(p))==sha for p,sha in sources.items()),'Menu stop source changed')
    trace=json.loads((output/'reentry-observation.json').read_text(encoding='utf-8'))['trace']
    events=json.loads((output/'recovery-observer.json').read_text(encoding='utf-8'))['events']
    menu=next(e for e in events if e['action']=='menu')
    require(trace['attach_preview_time_ns']<menu['virtual_time_ns'],'Debugger did not cover the first MENU input')
    receipt={'schema':1,'version':'2026.11.04-menu-stop-r111','result_sha256':digest(output/'result.json'),
        'parent_receipt_sha256':digest(output/'app-transition-observation.json'),'source_sha256':sources,
        'attached_preview_ns':trace['attach_preview_time_ns'],'first_MENU_ns':menu['virtual_time_ns'],
        'functional_acceptance_eligible':False,'camera_accessed':False,'AF_modified':False,'guest_memory_or_registers_written':False}
    with (output/'menu-stop-observation.json').open('x',encoding='utf-8') as handle:json.dump(receipt,handle,ensure_ascii=False,indent=2)
    print(json.dumps({k:v for k,v in receipt.items() if k!='source_sha256'}),flush=True)
    return result,receipt


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--qemu',type=Path,default=parent.parent.recovery.parent.hardware.DEFAULT_QEMU)
    for name in ('card','group23','fixture','output'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--gdb',type=Path,default=parent.parent.recovery.host_capture.DEFAULT_GDB)
    parser.add_argument('--duration',type=float,default=24);parser.add_argument('--wall-limit',type=float,default=600)
    args=parser.parse_args();result,receipt=run(args.qemu,args.card,args.group23,args.fixture,args.output,args.gdb,args.duration,args.wall_limit)
    raise SystemExit(0 if result['completed_observation'] and not result.get('failure') and result.get('process_exit_code')==0 else 1)
