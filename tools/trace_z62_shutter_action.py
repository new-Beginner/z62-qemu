"""Observe full-press dispatch, original APPLV changed-input predicate and ring commit."""
import argparse
from pathlib import Path
from trace_z62_shutter_route import run

POINTS = {0x1029A9BA:'application-input-dispatch', 0x10540246:'applv-input-method',
          0x1053EDDA:'input-change-predicate-return', 0x1053EE7E:'input-ring-commit-return'}
STATE = {0xC1818D34:4, 0xC1811E50:40, 0xC181D330:32, 0xC201FCB0:24}

if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--card',type=Path,required=True)
    args=p.parse_args()
    result=run(args.output,args.card,extra_points=POINTS,extra_state=STATE)
    print(result['summary'])
    raise SystemExit(0 if result['shutter_route_observation_completed'] else 1)
