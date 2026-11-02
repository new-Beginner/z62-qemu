"""Inspect original mode-handler policy only after the firmware declares readiness."""
import argparse
from pathlib import Path
from trace_z62_shutter_route import run
from trace_z62_shutter_policy import POINTS, STATE

if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--card',type=Path,required=True)
    args=p.parse_args()
    result=run(args.output,args.card,only_points=POINTS,
               extra_state={**STATE,0xC1868AE8:1,0xC23D9F14:5},
               max_stops=300,wait_for_ready=True,duration=45)
    print(result['summary'])
    raise SystemExit(0 if result['shutter_route_observation_completed'] else 1)
