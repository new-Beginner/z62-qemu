"""The unchanged original three-stage scenario on the r66 ownership model."""
import argparse
from contextlib import redirect_stdout
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch
import trace_z62_paired_ingress_lifecycle as parent
import run_z62_paired_handoff as host

VERSION='2026.11.03-paired-handoff-lifecycle-r66'


def run(output, card, group23, qemu, duration=55):
    build=host.verify_build(qemu)
    source=Path(__file__); initial=hashlib.sha256(source.read_bytes()).hexdigest()
    with patch.object(parent,'host',host), patch.object(parent,'FIELDS',
            {**parent.FIELDS,'retired-notifications':int}):
        observed=parent.run(output,card,group23,qemu,duration)
    unchanged=hashlib.sha256(source.read_bytes()).hexdigest()==initial
    result={**observed,'version':VERSION,'build':build,
        'inherited_result_sha256':hashlib.sha256((output/'paired-ingress-lifecycle.json').read_bytes()).hexdigest(),
        'source_sha256':{**observed['source_sha256'],str(source):initial},
        'sources_unchanged_during_run':observed['sources_unchanged_during_run'] and unchanged,
        'completed_observation':observed['completed_observation'] and unchanged,
        'functional_acceptance_eligible':observed['functional_acceptance_eligible'] and unchanged,
        'old_notification_is_not_a_completion':True}
    with (output/'paired-handoff-lifecycle.json').open('x',encoding='utf-8') as handle:
        json.dump(result,handle,indent=2)
    print(json.dumps({k:result[k] for k in ('completed_observation','process_closed',
        'strict_mode_recovery_verified','video_new_pixels_reached_factory_lcd',
        'photo_return_new_pixels_reached_factory_lcd')},indent=2),flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True); parser.add_argument('--card',type=Path,required=True)
    parser.add_argument('--group23',type=Path,required=True); parser.add_argument('--qemu',type=Path,default=host.DEFAULT_QEMU)
    parser.add_argument('--duration',type=float,default=55); args=parser.parse_args()
    if not 55<=args.duration<=90:
        parser.error('Full scenario needs 55..90 seconds')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.with_name(args.output.name+'-stdout.txt').open('x',encoding='utf-8') as log:
        with redirect_stdout(parent.control.parent.video.lifecycle.Tee(sys.stdout,log)):
            result=run(args.output,args.card,args.group23,args.qemu.resolve(),args.duration)
    raise SystemExit(0 if result['completed_observation'] else 1)
