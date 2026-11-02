"""Test the original absent-lens path using only its recovered external PG0."""
import argparse
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import trace_z62_shutter_route as route
import run_z62_capture_contacts as host
import z62_lens_contact as lens
from trace_z62_lens_control import context
from trace_z62_capture_contact_route import fanout


def run(output, card, group23, absent, capture, duration, *,
        extra_points=None, extra_state=None, extra_hit_hook=None, breakpoint_window=None,
        max_stops=500, extra_observation_hook=None, read_watchpoints=None, automatic_shutter=True, wall_limit=None,
        observation_timeout_recovery=False):
    fixture = group23.resolve(strict=True)
    expected = 'c7dd14358b45b2813fdee85fc587bcdd5899f7a81e0d5830513d631235bcc700'
    if not str(fixture).isascii() or ',' in str(fixture) or hashlib.sha256(fixture.read_bytes()).hexdigest() != expected:
        raise ValueError('Expected the explicit experimental NOR23 fixture')
    host.verify_build(host.DEFAULT_QEMU)
    original_configure = route.host.configure_command
    original_apply = route.shutter.apply_console
    def configure(command, *a, **kw):
        result = host.configure_command(original_configure(command, *a, **kw), capture)
        return result + ['-device', f'loader,file={fixture},addr=0x13420000,force-raw=on']
    def apply(source):
        original_apply(source)
        if absent:
            lens.apply_console(source)
    points = {0x10239734: 'raw-buffer-descriptor',
              0x080311C4: 'controller-lens-report-entry',
              0x080311F4: 'controller-lens-report-fields',
              0x102F38F4: 'lens-detection-input',
              0x10347DD6: 'lens-present-state-set'}
    if capture:
        points.update({0x1022C28A: 'capture-full-request',
                       0x1022B630: 'capture-next-state-return',
                       0x1022D1A6: 'capture-enter-state3',
                       0x1022D230: 'capture-enter-state0'})
    points.update(extra_points or {})
    state = {0xC188A210: 16, 0xC293D28C: 18, 0xC23E3F24: 64,
             0xC1869780: 22, 0xC1821EB8: 1, 0xC1868AE8: 1}
    state.update(extra_state or {})
    def hit(remote, registers):
        result = context(remote, registers)
        if extra_hit_hook is not None:
            result.update(extra_hit_hook(remote, registers))
        return result
    with patch.object(route.host, 'DEFAULT_QEMU', host.DEFAULT_QEMU), \
         patch.object(route.host, 'configure_command', configure), \
         patch.object(route.shutter, 'apply_console', apply):
        result = route.run(output, card, only_points=points,
                           extra_state=state, extra_hit_hook=hit,
                           wait_for_ready=capture, duration=duration, max_stops=max_stops,
                           breakpoint_window=breakpoint_window,
                           extra_observation_hook=extra_observation_hook,
                           read_watchpoints=read_watchpoints,
                           automatic_shutter=automatic_shutter,
                           wall_limit=wall_limit,
                           observation_timeout_recovery=observation_timeout_recovery,
                           extra_contact_hook=fanout if capture else None)
    receipt = {'schema': 1, 'absent_lens': absent, 'capture_contacts': capture,
               'input_adapter': lens.identity() if absent else None,
               'group23': {'path': str(fixture), 'sha256': expected, 'factory_calibration': False},
               'observation_completed': bool(result.get('capture_setup_observed') and
                                             result.get('stop_reason') == 'virtual limit')}
    if capture:
        receipt['observation_completed'] &= result['shutter_route_observation_completed']
    with (output / 'fixture.json').open('x', encoding='utf-8') as handle:
        json.dump(receipt, handle, indent=2)
    return result, receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--card', type=Path, required=True)
    parser.add_argument('--group23', type=Path, required=True)
    parser.add_argument('--absent', action='store_true')
    parser.add_argument('--capture', action='store_true')
    parser.add_argument('--duration', type=float)
    args = parser.parse_args()
    duration = args.duration if args.duration is not None else (42 if args.capture else 3)
    if not 2 <= duration <= 60 or (args.capture and duration < 36):
        parser.error('duration must be 2..60, or 36..60 for capture')
    result, receipt = run(args.output, args.card, args.group23, args.absent, args.capture, duration)
    print(result['summary'])
    print(receipt)
    raise SystemExit(0 if receipt['observation_completed'] else 1)
