"""Trace original ready notifications and the two-bit join behind shutter enable."""
import argparse
from pathlib import Path
from trace_z62_shutter_route import run

POINTS = {0x10239734:'raw-buffer-descriptor', 0x103161E8:'operation-ready-producer',
          0x1031A23E:'ready-join-bit1-producer', 0x1031A24A:'ready-join-test',
          0x103EE908:'ready-notification-translate', 0x104AD33A:'application-event-post',
          0x10541366:'input-inhibit-clear-call', 0x105B3358:'input-inhibit-setter'}
STATE = {0xC1868A70:36, 0xC18694B0:8, 0xC201BEA0:6, 0xC181C9C4:2,
         0xC1821EB4:6, 0xC1818D34:4}

if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--card',type=Path,required=True)
    args=p.parse_args()
    result=run(args.output,args.card,only_points=POINTS,extra_state=STATE,max_stops=600)
    print(result['summary'])
    raise SystemExit(0 if result['shutter_route_observation_completed'] else 1)
