"""r109 original APPLV reentry functions over the frozen r104 kernel."""
import argparse
import json
from pathlib import Path
from unittest.mock import patch
import probe_z62_cw_app_transition as parent
import z62_cw_app_transition_observer as old
import z62_applv_reentry_observer as current
from record_z62_action_evidence import workspace,digest,require


def run(qemu,card,group23,fixture,output,gdb,duration=24,wall_limit=600):
    output=workspace(output)
    sources={str(Path(p).resolve()):digest(Path(p)) for p in (__file__,parent.__file__,current.__file__)}
    with (patch.object(old,'AppTransitionObserver',current.ApplvReentryObserver),
            patch.object(old,'POINTS',current.POINTS),patch.object(old,'CALLS',current.CALLS),
            patch.object(old,'contract',current.contract)):
        result,prior=parent.run(qemu,card,group23,fixture,output,gdb,duration,wall_limit)
    require(all(digest(Path(p))==sha for p,sha in sources.items()),'APPLV observer changed')
    receipt={'schema':1,'version':'2026.11.04-APPLV-reentry-r109','result_sha256':digest(output/'result.json'),
        'parent_receipt_sha256':digest(output/'app-transition-observation.json'),'source_sha256':sources,
        'functional_acceptance_eligible':False,'camera_accessed':False,'AF_modified':False,
        'guest_memory_or_registers_written':False}
    with (output/'applv-reentry-observation.json').open('x',encoding='utf-8') as handle:json.dump(receipt,handle,ensure_ascii=False,indent=2)
    print(json.dumps({k:v for k,v in receipt.items() if k!='source_sha256'}),flush=True)
    return result,receipt


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--qemu',type=Path,default=parent.parent.recovery.parent.hardware.DEFAULT_QEMU)
    for name in ('card','group23','fixture','output'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--gdb',type=Path,default=parent.parent.recovery.host_capture.DEFAULT_GDB)
    parser.add_argument('--duration',type=float,default=24);parser.add_argument('--wall-limit',type=float,default=600)
    args=parser.parse_args();result,receipt=run(args.qemu,args.card,args.group23,args.fixture,args.output,args.gdb,args.duration,args.wall_limit)
    raise SystemExit(0 if result['completed_observation'] and not result.get('failure') and result.get('process_exit_code')==0 else 1)
