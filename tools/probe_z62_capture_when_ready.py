"""Wait for original readiness before a physical two-stage shutter sequence.

Only reads readiness fields; does not clear the inhibit latch or force a ready
event. If readiness never arrives, no shutter contacts are driven.
"""
import argparse
from pathlib import Path
from probe_z62_shutter_capture import run

if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    result=run(args.output,wait_for_ready=True,duration=100,wall_limit=2700)
    experiment=result['shutter_capture_experiment']
    print('original_readiness=',experiment['readiness_receipt'])
    print('contacts=',experiment['events'])
    raise SystemExit(0 if result['observation_completed'] and experiment['readiness_receipt'] and
                     len(experiment['events'])==4 else 1)
