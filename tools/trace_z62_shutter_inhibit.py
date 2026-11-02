"""Trace the original producer/clearer of C1821EB8; never modify the latch."""
import argparse
from pathlib import Path
from trace_z62_shutter_route import run

POINTS = {0x10239734:'raw-buffer-descriptor', 0x105B3358:'input-inhibit-setter',
          0x10542B48:'applv-transition-entry', 0x10541366:'input-inhibit-clear-call',
          0x1054302E:'status-a-return', 0x10543034:'status-b-return',
          0x1054303A:'status-c-return', 0x105430E8:'transition-flag2a-return',
          0x105430EE:'transition-mode-a-return', 0x105430F4:'transition-mode-b-return',
          0x105430FA:'transition-mode-c-return'}
STATE = {0xC1821EB4:6, 0xC1818D34:4, 0xC181D9A0:32, 0xC181D330:32}

if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--card',type=Path,required=True)
    args=p.parse_args()
    result=run(args.output,args.card,only_points=POINTS,extra_state=STATE,max_stops=300)
    print(result['summary'])
    raise SystemExit(0 if result['shutter_route_observation_completed'] else 1)
