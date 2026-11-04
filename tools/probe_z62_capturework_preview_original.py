"""Original r104 source-cohort/preview qualification, no guest ready or event6 injection."""
import argparse
import json
from pathlib import Path
from unittest.mock import patch
import probe_z62_readout_statistics_no_debugger as parent
import run_z62_capturework_preview as hardware
from record_z62_action_evidence import workspace,digest,require


def run(qemu,card,group23,fixture,output,duration=24,wall_limit=600):
    qemu,output=map(workspace,(qemu,output));hardware.verify_build(qemu)
    stream=parent.parent.parent.finite.parent
    previous_snapshot=stream.original.snapshot;previous_configure=stream.input_driver.statistics.command_profile
    sources={str(Path(p)):digest(Path(p)) for p in (__file__,hardware.__file__,parent.__file__)}
    def configure(*args,**kwargs):
        return previous_configure(*args,**kwargs)+['-global','nikon-z72-input-config.z62-capturework-preview=on']
    def snapshot(machine,layout):
        row=previous_snapshot(machine,layout)
        row['CW_cohort']=json.loads(machine.qmp.command('qom-get',{'path':'/machine/master-input','property':'capturework-cohort-status'}))
        row['CW_preview_source']=json.loads(machine.qmp.command('qom-get',{
            'path':machine.capturework_boot_path,'property':'capturework-preview-status'}))
        row['metadata_clock_completions']=machine.qmp.command('qom-get',{
            'path':'/machine/master-input','property':'metadata-completions'})
        return row
    with (patch.object(stream.input_driver.statistics,'command_profile',configure),
            patch.object(stream.original,'snapshot',snapshot)):
        result,prior=parent.run(qemu,card,group23,fixture,output,duration,wall_limit)
    require(all(digest(Path(p))==sha for p,sha in sources.items()),'CW preview observation source changed')
    receipt={'schema':1,'version':'2026.11.04-CW-preview-original-r104',
        'result_sha256':digest(output/'result.json'),'source_sha256':sources,'camera_accessed':False,
        'metadata_event6_injected':False,'legacy_RAW_counters_modified':False,
        'firmware_software_or_ready_modified':False,'GDB_attached':False}
    with (output/'capturework-preview-stream.json').open('x',encoding='utf-8') as handle:
        json.dump(receipt,handle,ensure_ascii=False,indent=2)
    return result,receipt


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--qemu',type=Path,default=hardware.DEFAULT_QEMU)
    parser.add_argument('--card',type=Path,required=True);parser.add_argument('--group23',type=Path,required=True)
    parser.add_argument('--fixture',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--duration',type=float,default=24);parser.add_argument('--wall-limit',type=float,default=600)
    args=parser.parse_args();result,receipt=run(args.qemu,args.card,args.group23,args.fixture,args.output,args.duration,args.wall_limit)
    raise SystemExit(0 if result['completed_observation'] and not result.get('failure') and result.get('process_exit_code')==0 else 1)
