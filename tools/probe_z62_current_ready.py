"""r96 passive original AND-wait/producer trace over the r95 reference input."""
import argparse
import json
from pathlib import Path
import traceback
from unittest.mock import patch
import probe_z62_group_parameter_input as parent
from z62_live_ready_observer import ReadyObserver
from record_z62_action_evidence import workspace,digest,require


def run(qemu,card,group23,fixture,output,duration=8,wall_limit=300):
    qemu,card,group23,fixture,output=map(workspace,(qemu,card,group23,fixture,output))
    observer=ReadyObserver(qemu);previous=parent.original.snapshot;source_hash=digest(Path(__file__))
    def snapshot(machine,layout):
        observer.tick(machine,layout)
        return previous(machine,layout)
    result=None
    try:
        with patch.object(parent.original,'snapshot',snapshot):
            result,_=parent.run(qemu,card,group23,fixture,output,duration,wall_limit)
    except Exception as exc:observer.record['driver_failure']={'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()}
    finally:
        try:observer.close()
        except Exception as exc:observer.record['cleanup_failure']={'type':type(exc).__name__,'message':str(exc)}
        require(digest(Path(__file__))==source_hash,'Ready driver changed')
        observer.record.setdefault('source_sha256',{})[str(Path(__file__))]=source_hash
        if (output/'result.json').is_file():observer.record['original_result_sha256']=digest(output/'result.json')
        observer.record['completed_observation']=len(observer.record['waits'])==3 and observer.record.get('detach')=='OK'
        with (output/'ready-observer.json').open('x',encoding='utf-8') as handle:json.dump(observer.record,handle,ensure_ascii=False,indent=2)
    print(json.dumps({k:observer.record.get(k) for k in ('completed_observation','driver_failure','cleanup_failure','detach','stops')},ensure_ascii=False),flush=True)
    return result,observer.record


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--qemu',type=Path,default=parent.hardware.DEFAULT_QEMU)
    parser.add_argument('--card',type=Path,required=True);parser.add_argument('--group23',type=Path,required=True)
    parser.add_argument('--fixture',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--duration',type=float,default=8);parser.add_argument('--wall-limit',type=float,default=300);args=parser.parse_args()
    result,record=run(args.qemu,args.card,args.group23,args.fixture,args.output,args.duration,args.wall_limit)
    raise SystemExit(0 if result and result['completed_observation'] and not result.get('failure') and record['completed_observation'] and not record.get('cleanup_failure') else 1)
