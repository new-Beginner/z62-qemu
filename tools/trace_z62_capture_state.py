"""Observe the original full-contact request and capture state transitions.

C23E3F76 is an original byte state, not a 32-bit error mask. This diagnostic
never modifies it. External MCU and capture GPIO contacts use verified r13.
"""
import argparse
from pathlib import Path
from unittest.mock import patch

import trace_z62_shutter_route as route
import run_z62_capture_contacts as host
from trace_z62_capture_contact_route import fanout

POINTS = {
    0x10239734: 'raw-buffer-descriptor',
    0x1022A8D8: 'original-full-contact-worker',
    0x1022C28A: 'capture-full-request',
    0x1022B620: 'capture-state-transition',
    0x1022B630: 'capture-next-state-return',
    0x1022B6BC: 'capture-state-byte-store',
    0x1022D1A6: 'capture-enter-state3',
    0x1022D230: 'capture-enter-state0',
}


def context(remote, registers):
    result = {'capture_context_192': remote.read(0xC23E3F64, 192).hex()}
    if registers['pc'] == 0x1022CE52:
        result['listener'] = hex(registers['r2'])
    if registers['pc'] in (0x1022CE52, 0x1022C28A):
        p = registers['r1'] if registers['pc'] == 0x1022CE52 else registers['r0']
        if 0xC0000000 <= p <= 0xDFFFFFF0:
            result['request_16'] = remote.read(p, 16).hex()
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--card', type=Path, required=True)
    parser.add_argument('--listeners', action='store_true',
                        help='also record frequent initialization listener traffic; may hit stop limit')
    args = parser.parse_args()
    if args.listeners:
        POINTS[0x1022CE52] = 'capture-listener-call'
    host.verify_build(host.DEFAULT_QEMU)
    original_configure = route.host.configure_command
    def configure(command, *a, **kw):
        return host.configure_command(original_configure(command, *a, **kw), True)
    with patch.object(route.host, 'DEFAULT_QEMU', host.DEFAULT_QEMU), \
         patch.object(route.host, 'configure_command', configure):
        result = route.run(args.output, args.card, only_points=POINTS,
                           extra_state={0xC23E3F64: 48, 0xC18697DC: 24, 0xC1869780: 22,
                                        0xC1821EB8: 1, 0xC1868AE8: 1},
                           extra_hit_hook=context, extra_contact_hook=fanout,
                           wait_for_ready=True, duration=40, max_stops=600)
    print(result['summary'])
    raise SystemExit(0 if result['shutter_route_observation_completed'] else 1)
