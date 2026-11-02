"""Observe actual 041B0040 publishers and the downstream ready join, without injection."""
import argparse
from pathlib import Path
from trace_z62_shutter_route import run

POINTS = {0x10239734:'raw-buffer-descriptor',
          0x1026AD1A:'frame-ready-publisher-a', 0x1026B008:'frame-ready-publisher-b',
          0x1026B860:'frame-ready-publisher-c', 0x103CF06C:'frame-ready-queue-output',
          0x103D0120:'frame-ready-forward', 0x10324602:'ready-join-dispatch-case',
          0x10322B50:'ready-join-bit2-producer', 0x10322B6A:'ready-join-completion-test',
          0x103EE908:'ready-notification-translate', 0x10541366:'input-inhibit-clear-call'}
STATE = {0xC1868A70:36, 0xC18694B0:8, 0xC201BEA0:6, 0xC1821EB4:6,
         0x20100000:9, 0x20102000:7, 0x20102100:7}

if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--card',type=Path,required=True)
    args=p.parse_args()
    result=run(args.output,args.card,only_points=POINTS,extra_state=STATE,max_stops=2400)
    print(result['summary'])
    raise SystemExit(0 if result['shutter_route_observation_completed'] else 1)
