"""Run original r98 with the r101 direct stop wait/sensor source observation."""
import argparse
import json
from pathlib import Path
from unittest.mock import patch
import probe_z62_finite_main_stream as finite
from z62_stop_wait_observer import StopWaitObserver,sensor_state
from z62_development_status import firmware_health
from record_z62_action_evidence import workspace,digest,require


def run(qemu,card,group23,fixture,output,duration=8,wall_limit=360):
    output=workspace(output);stream=finite.parent
    previous_run=stream.run;previous_snapshot=stream.original.snapshot
    sources={str(Path(p)):digest(Path(p)) for p in (__file__,__import__('z62_stop_wait_observer').__file__,finite.__file__)}
    def observed_run(qemu,card,group23,fixture,output,duration,wall_limit,observe,legacy_finite):
        return previous_run(qemu,card,group23,fixture,output,duration,wall_limit,True,legacy_finite)
    def snapshot(machine,layout):
        row=previous_snapshot(machine,layout);row.update(firmware_health(machine))
        row['sensor_source']={prop:machine.qmp.command('qom-get',{'path':'/machine/master-sensor','property':prop})
            for prop in ('raw-source-events','raw-completions','init-completions')}
        return row
    with (patch.object(stream,'ReadyObserver',StopWaitObserver),patch.object(stream,'run',observed_run),
            patch.object(stream.original,'snapshot',snapshot)):
        result=finite.run(qemu,card,group23,fixture,output,duration,wall_limit)
    require(all(digest(Path(p))==sha for p,sha in sources.items()),'Stop wait observer source changed')
    observed=result['ready_observer']
    receipt={'schema':1,'version':'2026.11.04-stop-wait-source-r101','result_sha256':digest(output/'result.json'),
        'source_sha256':sources,'waits':len(observed['waits']),'detach':observed.get('detach'),
        'camera_accessed':False,'functional_acceptance_eligible':False}
    with (output/'stop-wait-source.json').open('x',encoding='utf-8') as handle:
        json.dump(receipt,handle,ensure_ascii=False,indent=2)
    return result,receipt


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--qemu',type=Path,default=finite.hardware.DEFAULT_QEMU)
    parser.add_argument('--card',type=Path,required=True);parser.add_argument('--group23',type=Path,required=True)
    parser.add_argument('--fixture',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--duration',type=float,default=8);parser.add_argument('--wall-limit',type=float,default=360)
    args=parser.parse_args();result,receipt=run(args.qemu,args.card,args.group23,args.fixture,args.output,args.duration,args.wall_limit)
    raise SystemExit(0 if result['completed_observation'] and not result.get('failure') and result.get('process_exit_code')==0 else 1)
