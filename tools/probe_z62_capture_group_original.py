"""Original C1.70/r93 group observation, preserving zero parameters as supplied."""
import argparse
import json
from pathlib import Path
from unittest.mock import patch
import probe_z62_capturework_statistics_original as previous
import run_z62_capture_group as hardware
from record_z62_action_evidence import workspace,digest,require


def run(qemu,card,group23,output,duration=8,wall_limit=300):
    qemu,card,group23,output=map(workspace,(qemu,card,group23,output))
    hardware.verify_build(qemu);profile=previous.command_profile;snapshot=previous.original.snapshot
    def configure(*args,**kwargs):
        return profile(*args,**kwargs)+['-global','nikon-z72-input-config.z62-capture-group=on']
    def observe(machine,layout):
        row=snapshot(machine,layout)
        row['capture_group']=json.loads(machine.qmp.command('qom-get',{
            'path':'/machine/master-input','property':'capture-group-status'}))
        return row
    before=digest(Path(__file__))
    with (patch.object(previous,'hardware',hardware),patch.object(previous,'command_profile',configure),
            patch.object(previous.original,'snapshot',observe),
            patch.object(previous,'VERSION','2026.11.04-capture-group-original-r93')):
        result=previous.run(qemu,card,group23,output,duration,wall_limit,True)
    require(digest(Path(__file__))==before,'Group original driver changed')
    summary={'schema':1,'result_sha256':digest(output/'result.json'),'source_sha256':{str(Path(__file__)):before},
        'original_zero_parameters_not_replaced':True,'camera_accessed':False,
        'completed_observation':result['completed_observation'],'group':result.get('final',{}).get('capture_group')}
    with (output/'group-window.json').open('x',encoding='utf-8') as handle:json.dump(summary,handle,ensure_ascii=False,indent=2)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--qemu',type=Path,default=hardware.DEFAULT_QEMU)
    parser.add_argument('--card',type=Path,required=True);parser.add_argument('--group23',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--duration',type=float,default=8)
    parser.add_argument('--wall-limit',type=float,default=300);args=parser.parse_args()
    result=run(args.qemu,args.card,args.group23,args.output,args.duration,args.wall_limit)
    raise SystemExit(0 if result['completed_observation'] and not result.get('failure') and result.get('process_exit_code')==0 else 1)
