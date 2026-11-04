"""r94e read-only image binding with explicit early hardware-clock qualification."""
import argparse
import json
from pathlib import Path
import probe_z62_group_parameter_image as parent
import z62_original_clock_guard as clock
from record_z62_action_evidence import workspace,digest


def run(qemu,card,group23,output,duration=8,wall_limit=300):
    qemu,card,group23,output=map(workspace,(qemu,card,group23,output))
    base=parent.parent.parent.parent.parent.previous.original
    with clock.qualified_snapshot(base) as samples:
        result,receipt,summary=parent.run(qemu,card,group23,output,duration,wall_limit)
    extra={'schema':1,'version':'2026.11.04-group-image-clock-r94e',
        'result_sha256':digest(output/'result.json'),'parameter_image_sha256':digest(output/'parameter-image.json'),
        'hardware_clock_qualification_reads':samples,'frequency_or_time_substituted':False,
        'source_sha256':{str(Path(p)):digest(Path(p)) for p in (__file__,clock.__file__)},'camera_accessed':False}
    with (output/'clock-qualification.json').open('x',encoding='utf-8') as handle:json.dump(extra,handle,ensure_ascii=False,indent=2)
    return result,summary


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--qemu',type=Path,default=parent.parent.parent.parent.hardware.DEFAULT_QEMU)
    parser.add_argument('--card',type=Path,required=True);parser.add_argument('--group23',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--duration',type=float,default=8)
    parser.add_argument('--wall-limit',type=float,default=300);args=parser.parse_args()
    result,summary=run(args.qemu,args.card,args.group23,args.output,args.duration,args.wall_limit)
    raise SystemExit(0 if result['completed_observation'] and not result.get('failure') and result.get('process_exit_code')==0
        and summary['images'] and all(r['complete_image_matches_staged_group17'] for r in summary['images'].values()) else 1)
