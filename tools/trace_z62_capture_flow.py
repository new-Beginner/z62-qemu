"""Observe original capture request, flow stages and completion on absent-lens r13.

Only external contacts are driven. Code breakpoints and RAM reads do not modify
firmware instructions, return values, ready flags or completion notifications.
The supplied virtual regular card is used with QEMU snapshot semantics.
"""
import argparse
from pathlib import Path

from probe_z62_no_lens import run


POINTS = {
    0x1022A2C0: 'capture-request-build',
    0x103ED3B6: 'capture-main-request',
    0x103ED296: 'capture-flow-zero-step',
    0x103ECEEC: 'capture-flow-normal-step',
    0x1022C5AC: 'capture-request-retire',
}
SUBMIT_POINTS = {
    0x10325186: 'capture-submit-wrapper',
    0x10320018: 'capture-submit-queued-worker',
    0x1031D760: 'capture-submit-event-test-return',
    0x1031D6FC: 'capture-submit-event-ready',
    0x1031D53E: 'capture-lower-setup',
    0x1031DF24: 'capture-lower-result',
}


def context(remote, registers):
    # Controller breakpoints share the hook, but have a separate address space.
    if registers['pc'] not in POINTS and registers['pc'] not in SUBMIT_POINTS:
        return {}
    data = remote.read(0xC23E2948, 0xA0)
    result = {'main_context_160': data.hex(),
              'flow': hex(int.from_bytes(data[4:8], 'little')),
              'stage': hex(int.from_bytes(data[8:12], 'little')),
              'callback': hex(int.from_bytes(data[12:16], 'little')),
              'callback_result': data[16]}
    if registers['pc'] == 0x103ED3B6:
        p = registers['r2']
        if 0xC0000000 <= p <= 0xDFFFFFD0:
            result['request_48'] = remote.read(p, 48).hex()
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--card', type=Path, required=True)
    parser.add_argument('--group23', type=Path, required=True)
    parser.add_argument('--submit-worker', action='store_true')
    args = parser.parse_args()
    points = {**POINTS, **SUBMIT_POINTS} if args.submit_worker else POINTS
    result, receipt = run(args.output, args.card, args.group23, True, True, 50 if args.submit_worker else 60,
                          extra_points=points, extra_state={0xC23E2948: 40, 0xC1868AC8: 8,
                                                           0xC23DBDE0: 24, 0xC23D9F14: 5},
                          extra_hit_hook=context)
    print(result['summary'])
    print(receipt)
    raise SystemExit(0 if receipt['observation_completed'] else 1)
