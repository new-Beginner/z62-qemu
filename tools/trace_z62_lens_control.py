"""Observe original lens requests and replies on r13, with known lab NOR23."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
from unittest.mock import patch

import trace_z62_shutter_route as route
import run_z62_capture_contacts as host

POINTS = {0x10239734: 'raw-buffer-descriptor',
          0x1043077C: 'system-lens-start', 0x10430822: 'system-lens-stop',
          0x104304E4: 'system-lens-result', 0x103EAA44: 'lens-operation-transition',
          0x102F0E1C: 'lens-command-submit'}


def context(remote, registers):
    pc = registers['pc']
    if pc in (0x080311C4, 0x080311F4):
        pointer = struct.unpack('<I', remote.read(0x20018A38, 4))[0]
        if not 0x20000000 <= pointer <= 0x2003FFF0:
            raise ValueError('Controller lens descriptor is not initialized')
        descriptor = remote.read(pointer, 16)
        _, _, port, mask = struct.unpack('<4I', descriptor)
        if port not in range(0x40020000, 0x40022400, 0x400):
            raise ValueError('Unexpected controller GPIO port')
        return {'controller_lens_frame_16': remote.read(0x20013E78, 16).hex(),
                'controller_stack_64': remote.read(registers['sp'], 64).hex(),
                'lens_descriptor_pointer': hex(pointer), 'lens_descriptor_16': descriptor.hex(),
                'lens_gpio_port': hex(port), 'lens_gpio_mask': hex(mask & 0xFFFF),
                'lens_gpio_mode_pull_idr': remote.read(port, 20).hex()}
    if pc == 0x10430584:
        p = registers['r0']
        if not 0xC0000000 <= p <= 0xDFFFFFE0:
            raise ValueError('System lens event outside RAM')
        data = remote.read(p, 28)
        words = struct.unpack('<7I', data)
        return {'policy_event_28': data.hex(), 'policy_event': hex(words[4]),
                'policy_value': hex(words[5])}
    if pc in (0x10430498, 0x104304B6, 0x1043075C):
        result = {'caller_stack_96': remote.read(registers['sp'], 96).hex()}
        if pc == 0x1043075C:
            result['caller_code_103eea20_48'] = remote.read(0x103EEA20, 48).hex()
            result['notification_10228136_16'] = remote.read(0x10228136, 16).hex()
        return result
    if pc == 0x102F0E1C:
        p = registers['r0']
        if not 0xC0000000 <= p <= 0xDFFFFFE0:
            raise ValueError('Lens descriptor outside RAM')
        data = remote.read(p, 28)
        words = struct.unpack('<7I', data)
        result = {'descriptor': hex(p), 'descriptor_28': data.hex()}
        payload = words[5]
        if 0xC0000000 <= payload <= 0xDFFFFFE0:
            result['payload_pointer'] = hex(payload)
            result['payload_32'] = remote.read(payload, 32).hex()
        return result
    if pc == 0x104304E4:
        p = registers['r1']
        if 0xC0000000 <= p <= 0xDFFFFFE0:
            return {'reply_pointer': hex(p), 'reply_32': remote.read(p, 32).hex()}
    return {}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--card', type=Path, required=True)
    parser.add_argument('--group23', type=Path, required=True)
    parser.add_argument('--policy', action='store_true')
    parser.add_argument('--presence', action='store_true')
    parser.add_argument('--errors', action='store_true')
    parser.add_argument('--error-writer', action='store_true')
    parser.add_argument('--watch-slot7', action='store_true')
    parser.add_argument('--detect', action='store_true')
    parser.add_argument('--watch-detect', action='store_true')
    parser.add_argument('--controller', action='store_true')
    args = parser.parse_args()
    if args.policy:
        POINTS = {0x10239734: 'raw-buffer-descriptor',
                  0x10430584: 'system-lens-policy-event',
                  0x10430498: 'system-lens-stop-request',
                  0x104304B6: 'system-lens-start-request',
                  0x1042F858: 'system-lens-start-completed',
                  0x10430890: 'system-lens-state-changed'}
    if args.presence:
        POINTS = {0x10239734: 'raw-buffer-descriptor',
                  0x1043075C: 'system-lens-presence-notice'}
    if args.errors:
        POINTS = {0x10239734: 'raw-buffer-descriptor',
                  0x102F0CA8: 'lens-error-reconnect-check',
                  0x10314C96: 'lens-connection-notice-producer'}
    if args.error_writer:
        POINTS = {0x10239734: 'raw-buffer-descriptor',
                  0x1034AB58: 'lens-link-status-compare',
                  0x1034ABD4: 'lens-error7-store',
                  0x10314C96: 'lens-connection-notice-producer'}
    if args.watch_slot7:
        POINTS = {0x10239734: 'raw-buffer-descriptor'}
    if args.detect:
        POINTS = {0x10239734: 'raw-buffer-descriptor',
                  0x102F38F4: 'lens-detection-input',
                  0x102F3940: 'lens-detection-policy-return',
                  0x10347DD6: 'lens-present-state-set'}
    if args.watch_detect:
        POINTS = {0x10239734: 'raw-buffer-descriptor'}
    if args.controller:
        POINTS = {0x10239734: 'raw-buffer-descriptor',
                  0x080311C4: 'controller-lens-report-entry',
                  0x080311F4: 'controller-lens-report-fields'}
    fixture = args.group23.resolve(strict=True)
    expected = 'c7dd14358b45b2813fdee85fc587bcdd5899f7a81e0d5830513d631235bcc700'
    if not str(fixture).isascii() or ',' in str(fixture) or hashlib.sha256(fixture.read_bytes()).hexdigest() != expected:
        raise ValueError('Requires the explicit reviewed zero-body NOR23 fixture')
    host.verify_build(host.DEFAULT_QEMU)
    original = route.host.configure_command
    def configure(command, *a, **kw):
        return original(command, *a, **kw) + ['-device', f'loader,file={fixture},addr=0x13420000,force-raw=on']
    with patch.object(route.host, 'DEFAULT_QEMU', host.DEFAULT_QEMU), \
         patch.object(route.host, 'configure_command', configure):
        result = route.run(args.output, args.card, only_points=POINTS,
                           extra_state={0xC186954C: 8, 0xC20985F0: 4, 0xC2098804: 24,
                                        0xC185DE80: 8, 0xC293D28C: 18, 0xC188A210: 16,
                                        0xC1869780: 22, 0xC23E3F24: 16},
                           extra_hit_hook=context, duration=3, max_stops=200,
                           write_watchpoints=({0xC18A7CC6: 1} if args.watch_detect else
                                              {0xC293D2A8: 4} if args.watch_slot7 else None))
    print(result['summary'])
    raise SystemExit(0 if result.get('capture_setup_observed') and
                     result.get('stop_reason') == 'virtual limit' else 1)
