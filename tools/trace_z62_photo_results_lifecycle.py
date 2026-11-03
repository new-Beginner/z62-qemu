"""Keep the exact selector scenario; opt into the observed r53 photo return."""
import argparse
from contextlib import redirect_stdout
import hashlib
import json
from pathlib import Path
from unittest.mock import patch
import sys

import trace_z62_grid_geometry_lifecycle as parent
import run_z62_photo_results as host

VERSION='2026.11.03-photo-results-lifecycle-r53'


def run(output,card,group23,qemu,retained=True,duration=55):
    with patch.object(parent,'host',host),patch.object(parent,'VERSION',VERSION):
        result=parent.run(output,card,group23,qemu,retained,duration)
    result={**result,'photo_entry_profile':VERSION,
            'photo_entry_source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'photo_result_layouts_enabled':True}
    with (output/'photo-results-lifecycle.json').open('x',encoding='utf-8') as handle:
        json.dump(result,handle,indent=2)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--card',type=Path,required=True)
    parser.add_argument('--group23',type=Path,required=True)
    parser.add_argument('--qemu',type=Path,default=host.DEFAULT_QEMU)
    parser.add_argument('--without-retained-input',action='store_true')
    parser.add_argument('--duration',type=float,default=55)
    args=parser.parse_args()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.with_name(args.output.name+'-stdout.txt').open('x',encoding='utf-8') as log:
        with redirect_stdout(parent.parent.pipeline.parent.Tee(sys.stdout,log)):
            result=run(args.output,args.card,args.group23,args.qemu.resolve(),not args.without_retained_input,args.duration)
    raise SystemExit(0 if result['completed_observation'] else 1)
