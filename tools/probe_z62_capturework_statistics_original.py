"""Independent r92 original-code window; preserve the frozen r90b driver.

Fix the experiment's missing card-detect qualification, enable the explicit
CW statistics route, and observe its source ownership without guest ready
writes, synthetic IRQ injection or legacy RAW counter changes.
"""
import argparse
import json
from pathlib import Path
from unittest.mock import patch

import probe_z62_capturework_original as original
import run_z62_capturework_statistics as hardware
from record_z62_action_evidence import workspace,digest,require

VERSION='2026.11.04-capturework-statistics-original-r92'


def command_profile(command,group23,policy0=True,bridge=True):
    require(policy0,'This experiment requires the explicit external MAIN policy')
    result=original_profile(command,group23,True)
    require(not any('nikon-z72-boot-config.z62-card-detect=' in x for x in result),
        'Card qualification already supplied')
    result+=['-global','nikon-z72-boot-config.z62-card-detect=on']
    if bridge: result+=['-global','nikon-z72-input-config.z62-capturework-statistics=on']
    return result


original_profile=original.command_profile


def run(qemu,card,group23,output,duration=8,wall_limit=300,bridge=True):
    qemu,card,group23,output=map(workspace,(qemu,card,group23,output))
    build=hardware.verify_build(qemu)
    sources=(Path(__file__),Path(original.__file__),Path(hardware.__file__))
    binding={str(path):digest(path) for path in sources}
    before=original.snapshot
    def snapshot(machine,layout):
        row=before(machine,layout)
        row['capturework_statistics']=json.loads(machine.qmp.command('qom-get',{
            'path':'/machine/master-input','property':'capturework-statistics-status'}))
        row['legacy_RAW_accepted']=machine.qmp.command('qom-get',{
            'path':'/machine/master-input','property':'raw-accepted'})
        return row
    def configure(command,group23,policy0=True): return command_profile(command,group23,policy0,bridge)
    with (patch.object(original,'command_profile',configure),patch.object(original,'snapshot',snapshot),
            patch.object(original,'VERSION',VERSION)):
        result=original.run(qemu,card,group23,output,duration,wall_limit,True)
    summary={'schema':1,'version':VERSION,'bridge_enabled':bridge,
        'card_detect_explicitly_enabled':True,'base_result_sha256':digest(output/'result.json'),
        'binary_sha256':build['binary_sha256'],'wrapper_sources_sha256':binding,
        'wrapper_sources_unchanged':all(digest(Path(name))==sha for name,sha in binding.items()),
        'original_window_completed':result['completed_observation'],
        'process_exit_code':result.get('process_exit_code'),'failure':result.get('failure'),
        'camera_accessed':False,'whole_camera_capture_AF_or_flash_safety_verified':False}
    with (output/'bridge-window.json').open('x',encoding='utf-8') as handle:
        json.dump(summary,handle,ensure_ascii=False,indent=2)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--qemu',type=Path,default=hardware.DEFAULT_QEMU)
    parser.add_argument('--card',type=Path,required=True); parser.add_argument('--group23',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True); parser.add_argument('--duration',type=float,default=8)
    parser.add_argument('--wall-limit',type=float,default=300); parser.add_argument('--bridge-off',action='store_true')
    args=parser.parse_args()
    result=run(args.qemu,args.card,args.group23,args.output,args.duration,args.wall_limit,not args.bridge_off)
    raise SystemExit(0 if result['completed_observation'] and result.get('process_exit_code')==0 and not result.get('failure') else 1)
