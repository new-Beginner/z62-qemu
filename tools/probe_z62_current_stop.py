"""r100: trace actual stop error composition upstream of original status 0x3f.

Same frozen r98 kernel, C inputs and source scheduler as r99. All selected
points are original Thumb function entries, except the already-verified status
append BL. The r99 observer records real LR/SP matched returns and raw stacks.
"""
import argparse
import json
from pathlib import Path
from unittest.mock import patch
import probe_z62_current_failure as parent
import z62_failure_observer as observer
from record_z62_action_evidence import workspace,digest,require

POINTS={0x102dbb9c:'capture-stop',0x102dd9c8:'mode0-stop',0x102dd964:'mode2-stop',
    0x102fb6e6:'mode0-substop-a',0x102fb640:'mode0-substop-b',0x102fcbae:'mode0-substop-c',
    0x102fb41c:'cleanup-a',0x102fb62a:'cleanup-b',0x102fb702:'cleanup-c',0x102fca50:'cleanup-d',
    0x1026d434:'capture-result-notification',0x103970d4:'status-append-call'}


def run(qemu,card,group23,fixture,output,duration=16,wall_limit=480):
    output=workspace(output);source_sha=digest(Path(__file__))
    with patch.object(observer,'POINTS',POINTS):
        result,prior=parent.run(qemu,card,group23,fixture,output,duration,wall_limit)
    require(digest(Path(__file__))==source_sha,'Stop observer configuration changed')
    receipt={'schema':1,'version':'2026.11.04-current-stop-r100','result_sha256':digest(output/'result.json'),
        'parent_receipt_sha256':digest(output/'failure-observation.json'),
        'source_sha256':{str(Path(__file__)):source_sha},'selected_original_points':{hex(k):v for k,v in POINTS.items()},
        'camera_accessed':False,'guest_state_written':False,'functional_acceptance_eligible':False}
    with (output/'stop-observation.json').open('x',encoding='utf-8') as handle:
        json.dump(receipt,handle,ensure_ascii=False,indent=2)
    return result,receipt


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qemu',type=Path,default=parent.finite.hardware.DEFAULT_QEMU)
    parser.add_argument('--card',type=Path,required=True);parser.add_argument('--group23',type=Path,required=True)
    parser.add_argument('--fixture',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--duration',type=float,default=16);parser.add_argument('--wall-limit',type=float,default=480)
    args=parser.parse_args();result,receipt=run(args.qemu,args.card,args.group23,args.fixture,args.output,args.duration,args.wall_limit)
    raise SystemExit(0 if result['completed_observation'] and not result.get('failure') and result.get('process_exit_code')==0 else 1)
