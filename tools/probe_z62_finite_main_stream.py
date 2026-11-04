"""r98 opt-in retained-source finite sampling on the independent MAIN stream."""
import argparse
import json
from pathlib import Path
from unittest.mock import patch
import probe_z62_main_stream as parent
import run_z62_capturework_finite as hardware
from record_z62_action_evidence import workspace,digest,require


def run(qemu,card,group23,fixture,output,duration=8,wall_limit=300):
    qemu,card,group23,fixture,output=map(workspace,(qemu,card,group23,fixture,output));hardware.verify_build(qemu)
    previous=parent.input_driver.statistics.command_profile
    def configure(*args,**kwargs):
        command=previous(*args,**kwargs)
        require(not any('z62-capturework-finite=' in value for value in command),'Finite source already selected')
        return command+['-global','nikon-z72-input-config.z62-capturework-finite=on']
    source_sha={str(Path(p)):digest(Path(p)) for p in (__file__,hardware.__file__)}
    prior_snapshot=parent.original.snapshot
    def snapshot(machine,layout):
        row=prior_snapshot(machine,layout)
        row['retained_finite_source']=json.loads(machine.qmp.command('qom-get',{
            'path':'/machine/master-input','property':'capturework-finite-status'}))
        return row
    with (patch.object(parent.input_driver.statistics,'command_profile',configure),
            patch.object(parent.original,'snapshot',snapshot)):
        result=parent.run(qemu,card,group23,fixture,output,duration,wall_limit,False,True)
    receipt={'schema':1,'version':'2026.11.04-finite-main-stream-r98','result_sha256':digest(output/'result.json'),
        'source_sha256':source_sha,'retained_source_explicitly_enabled':True,
        'finite_samples_are_not_new_RAW_acquisitions':True,'camera_accessed':False}
    with (output/'finite-stream.json').open('x',encoding='utf-8') as handle:json.dump(receipt,handle,ensure_ascii=False,indent=2)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--qemu',type=Path,default=hardware.DEFAULT_QEMU)
    parser.add_argument('--card',type=Path,required=True);parser.add_argument('--group23',type=Path,required=True)
    parser.add_argument('--fixture',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--duration',type=float,default=8);parser.add_argument('--wall-limit',type=float,default=300);args=parser.parse_args()
    result=run(args.qemu,args.card,args.group23,args.fixture,args.output,args.duration,args.wall_limit)
    raise SystemExit(0 if result['completed_observation'] and not result.get('failure') and result.get('process_exit_code')==0 else 1)
