"""Run the actual DMA/ownership suite against r59b, preserving r59 failure."""
import argparse
import json
from pathlib import Path
from unittest.mock import patch
import probe_z62_video_isp as probe
import run_z62_video_isp_format as host


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qemu',type=Path,default=host.DEFAULT_QEMU)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists(): raise FileExistsError('Existing r59b native evidence is immutable')
    try:
        with patch.object(probe,'host',host): record=probe.check(args.qemu.resolve())
    except Exception as exc:
        record={'schema':1,'completed':False,'camera_accessed':False,
                'failure':{'type':type(exc).__name__,'message':str(exc)}}
    with args.output.open('x',encoding='utf-8') as handle: json.dump(record,handle,indent=2)
    print(json.dumps(record),flush=True)
    raise SystemExit(0 if record['completed'] else 1)
