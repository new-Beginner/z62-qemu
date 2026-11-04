"""r100b stop functions without per-frame zero-result notification traffic."""
import argparse
import json
from pathlib import Path
from unittest.mock import patch
import probe_z62_current_stop as parent
from record_z62_action_evidence import workspace,digest,require


def run(qemu,card,group23,fixture,output,duration=16,wall_limit=480):
    output=workspace(output)
    sources={str(Path(p)):digest(Path(p)) for p in (__file__,parent.__file__)}
    points={pc:name for pc,name in parent.POINTS.items() if name!='capture-result-notification'}
    with patch.object(parent,'POINTS',points):
        result,prior=parent.run(qemu,card,group23,fixture,output,duration,wall_limit)
    require(all(digest(Path(p))==sha for p,sha in sources.items()),'Scoped stop observer changed')
    receipt={'schema':1,'version':'2026.11.04-current-stop-r100b','result_sha256':digest(output/'result.json'),
        'source_sha256':sources,'per_frame_notification_entry_removed':True,'camera_accessed':False}
    with (output/'scoped-stop-observation.json').open('x',encoding='utf-8') as handle:
        json.dump(receipt,handle,ensure_ascii=False,indent=2)
    return result,receipt


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qemu',type=Path,default=parent.parent.finite.hardware.DEFAULT_QEMU)
    parser.add_argument('--card',type=Path,required=True);parser.add_argument('--group23',type=Path,required=True)
    parser.add_argument('--fixture',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--duration',type=float,default=16);parser.add_argument('--wall-limit',type=float,default=480)
    args=parser.parse_args();result,receipt=run(args.qemu,args.card,args.group23,args.fixture,args.output,args.duration,args.wall_limit)
    raise SystemExit(0 if result['completed_observation'] and not result.get('failure') and result.get('process_exit_code')==0 else 1)
