"""Identify the original action-0x14 destination and final gate results."""
import argparse
from pathlib import Path
from trace_z62_shutter_route import run

POINTS = {0x10239734:'raw-buffer-descriptor',
          0x10544C4A:'application-action-selected',
          0x10545080:'application-action-gate-return',
          0x105B1F44:'mode-action-callback'}
STATE = {0xC1818D34:4, 0xC181D330:32, 0xC201CC04:12, 0xC181D9A0:24}

if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--card',type=Path,required=True)
    args=p.parse_args()
    result=run(args.output,args.card,only_points=POINTS,extra_state=STATE,max_stops=3000)
    print(result['summary'])
    raise SystemExit(0 if result['shutter_route_observation_completed'] else 1)
