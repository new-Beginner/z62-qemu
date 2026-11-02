"""Observe only action-driven mode-handler decisions, excluding shared startup work.

104E4258 also runs repeatedly before any shutter input; it is not established
as a photo/exposure request. The older broad gate probe is kept as evidence.
"""
import argparse
from pathlib import Path
from trace_z62_shutter_route import run

POINTS = {
    0x10239734:'raw-buffer-descriptor', 0x104E97AC:'mode-action-entry',
    0x104E97B8:'mode-inhibit-return', 0x104E97CC:'action-class-a-return',
    0x104E97D4:'action-class-b-return', 0x104E97DC:'action-class-c-return',
    0x104E97EA:'alternate-action-gate-return', 0x104E9800:'mode-policy-return',
    0x104E9830:'mode-policy-test', 0x104E983C:'mode-shared-work-call',
}
STATE = {0xC1818D34:4, 0xC181D330:32, 0xC201CC04:12, 0xC181D9A0:24,
         0xC1821EB8:1, 0xC202C0E4:2, 0xC202CA48:2}

if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--card',type=Path,required=True)
    args=p.parse_args()
    result=run(args.output,args.card,only_points=POINTS,extra_state=STATE,max_stops=300)
    print(result['summary'])
    raise SystemExit(0 if result['shutter_route_observation_completed'] else 1)
