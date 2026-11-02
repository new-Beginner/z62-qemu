"""Record original action-14 shooting decisions without overriding any result."""
import argparse
from pathlib import Path
from trace_z62_shutter_route import run

POINTS = {
    0x10239734:'raw-buffer-descriptor', 0x104E97AC:'shoot-mode-action',
    0x104E97B8:'shoot-inhibit-return', 0x104E97CC:'action-class-a-return',
    0x104E97D4:'action-class-b-return', 0x104E97DC:'action-class-c-return',
    0x104E97EA:'alternate-action-gate-return', 0x104E9800:'shoot-policy-return',
    0x104E9830:'shoot-policy-test', 0x104E4258:'exposure-request-entry',
    0x104E4296:'exposure-blocked-return', 0x104E429E:'exposure-readiness-return',
    0x104E42A6:'exposure-clock-return', 0x104E42C8:'exposure-state-return',
    0x104E42D0:'exposure-condition-a-return', 0x104E42D6:'exposure-condition-b-return',
    0x104E42DC:'exposure-condition-c-return', 0x104E42E2:'exposure-condition-d-return',
    0x104E42E8:'exposure-condition-e-return', 0x104E42EE:'exposure-condition-f-return',
    0x104E431E:'exposure-fallback-return',
}
STATE = {0xC1818D34:4, 0xC181D330:32, 0xC201CC04:12, 0xC181D9A0:24}

if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--card',type=Path,required=True)
    args=p.parse_args()
    result=run(args.output,args.card,only_points=POINTS,extra_state=STATE,max_stops=1000)
    print(result['summary'])
    raise SystemExit(0 if result['shutter_route_observation_completed'] else 1)
