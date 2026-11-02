"""Observe real stop waits/idle checks and lifecycle notifications on r9."""
import argparse
from pathlib import Path
import trace_z62_preview_lifecycle as lifecycle

POINTS={**lifecycle.POINTS,
    0x103B7356:'wait-call',0x103B735A:'wait-return',
    0x103B73AE:'wait-call',0x103B73B2:'wait-return',
    0x103B73A0:'unit-idle-query-return',0x103B73C2:'unit-idle-test',
    0x1038AFCE:'bank-stop-lifecycle',0x1038B01C:'image-client-notification',
    0x10264930:'raw-upper-stop-flag-write'}
STATE={**lifecycle.STATE,0xC18094E4:32,0xC18647D8:64,0xC1D52600:40}


def run(output):
    old=lifecycle.POINTS,lifecycle.STATE
    lifecycle.POINTS,lifecycle.STATE=POINTS,STATE
    try: return lifecycle.run(output,duration=38)
    finally: lifecycle.POINTS,lifecycle.STATE=old


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();r=run(args.output)
    print(r['summary'])
    raise SystemExit(0 if r['capture_setup_observed'] else 1)
