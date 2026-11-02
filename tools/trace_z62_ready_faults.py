"""Sparse CPU-fault and queue observations after first preview, avoiding per-frame stops."""
import argparse
from pathlib import Path
from trace_z62_shutter_route import run
from trace_z62_ready_queue import faults

POINTS = {0x10239734:'raw-buffer-descriptor', 0x104E97AC:'mode-action-entry'}
STATE = {0xC23D9EE8:32, 0xC1868A70:36, 0xC201BEA0:6, 0xC1821EB4:6}

if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--card',type=Path,required=True)
    args=p.parse_args()
    result=run(args.output,args.card,only_points=POINTS,extra_state=STATE,max_stops=60,extra_hit_hook=faults)
    print(result['summary'])
    raise SystemExit(0 if result['shutter_route_observation_completed'] else 1)
