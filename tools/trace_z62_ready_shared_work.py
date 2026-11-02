"""Trace shared-work decisions only inside an original ready full-press call."""
import argparse
from pathlib import Path
from trace_z62_shutter_route import run

SHARED = {
    0x104E4258:'shared-work-entry', 0x104E4296:'shared-condition-a-return',
    0x104E429E:'shared-condition-b-return', 0x104E42A6:'shared-clock-return',
    0x104E42C8:'shared-state-return', 0x104E42D0:'shared-condition-c-return',
    0x104E42D6:'shared-condition-d-return', 0x104E42DC:'shared-condition-e-return',
    0x104E42E2:'shared-condition-f-return', 0x104E42E8:'shared-condition-g-return',
    0x104E42EE:'shared-condition-h-return', 0x104E431E:'shared-fallback-return',
}
POINTS = {0x10239734:'raw-buffer-descriptor',0x104E97AC:'mode-action-entry',
          0x1054512A:'mode-action-caller-return',**SHARED}
STATE = {0xC1821EB8:1,0xC1868AE8:1,0xC181D330:32,0xC23D9F14:5}
WINDOW = {'entry':0x104E97AC,'return_pc':0x1054512A,'register':'r0','equals':0x14,
          'points':list(SHARED)}

if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--card',type=Path,required=True)
    args=p.parse_args()
    result=run(args.output,args.card,only_points=POINTS,extra_state=STATE,max_stops=600,
               wait_for_ready=True,duration=45,breakpoint_window=WINDOW)
    print(result['summary'])
    print(result.get('breakpoint_window_events'))
    ok=result['shutter_route_observation_completed'] and not result.get('breakpoint_window_active',True)
    raise SystemExit(0 if ok else 1)
