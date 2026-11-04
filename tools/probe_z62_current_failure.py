"""Observe original r98 error publication and finite consumer calls, unchanged kernel."""
import argparse
import json
from pathlib import Path
from unittest.mock import patch
import probe_z62_finite_main_stream as finite
import z62_development_status as health
from z62_failure_observer import FailureObserver
from record_z62_action_evidence import workspace,digest,require


def run(qemu,card,group23,fixture,output,duration=16,wall_limit=480):
    qemu,card,group23,fixture,output=map(workspace,(qemu,card,group23,fixture,output))
    stream=finite.parent;previous_run=stream.run;previous_snapshot=stream.original.snapshot
    source_sha={str(Path(p)):digest(Path(p)) for p in (__file__,
        __import__('z62_failure_observer').__file__,finite.__file__)}
    def observed_run(qemu,card,group23,fixture,output,duration,wall_limit,observe,legacy_finite):
        return previous_run(qemu,card,group23,fixture,output,duration,wall_limit,True,legacy_finite)
    def snapshot(machine,layout):
        result=previous_snapshot(machine,layout);result.update(health.firmware_health(machine));return result
    with (patch.object(stream,'ReadyObserver',FailureObserver),patch.object(stream,'run',observed_run),
            patch.object(stream.original,'snapshot',snapshot)):
        result=finite.run(qemu,card,group23,fixture,output,duration,wall_limit)
    observed=result['ready_observer']
    require(all(digest(Path(p))==sha for p,sha in source_sha.items()),'Failure observer source changed')
    receipt={'schema':1,'version':'2026.11.04-current-failure-r99',
        'result_sha256':digest(output/'result.json'),'source_sha256':source_sha,
        'completed_observation':result['completed_observation'],'process_exit_code':result.get('process_exit_code'),
        'observer_detach':observed.get('detach'),'calls':len(observed['calls']),'returns':len(observed['returns']),
        'original_status_append_codes':[r['registers']['r0'] for r in observed['calls'] if r['label']=='status-append-call'],
        'camera_accessed':False,'functional_acceptance_eligible':False}
    with (output/'failure-observation.json').open('x',encoding='utf-8') as handle:
        json.dump(receipt,handle,ensure_ascii=False,indent=2)
    print(json.dumps({k:v for k,v in receipt.items() if k!='source_sha256'}),flush=True)
    return result,receipt


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--qemu',type=Path,default=finite.hardware.DEFAULT_QEMU)
    parser.add_argument('--card',type=Path,required=True);parser.add_argument('--group23',type=Path,required=True)
    parser.add_argument('--fixture',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--duration',type=float,default=16);parser.add_argument('--wall-limit',type=float,default=480)
    args=parser.parse_args();result,receipt=run(args.qemu,args.card,args.group23,args.fixture,args.output,args.duration,args.wall_limit)
    raise SystemExit(0 if result['completed_observation'] and not result.get('failure') and result.get('process_exit_code')==0 else 1)
