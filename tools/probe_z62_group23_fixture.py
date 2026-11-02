"""Test a separately labelled zero-body group23 NOR storage hypothesis.

The original C1.70 directory specifies flash 13420000, storage bytes E0000,
and workspace D8000. ENDM is the existing parameter-container convention.
No factory calibration is known. This does not patch code or readiness flags.
The diagnostic loader stays outside the normal console/parameter profile.
"""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

import trace_z62_shutter_route as route
import run_z62_capture_contacts as host
from trace_z62_capture_components import context
from trace_z62_capture_contact_route import fanout


def image():
    data = bytearray(0xE0000)
    data[-4:] = b'ENDM'
    return bytes(data)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--card', type=Path, required=True)
    parser.add_argument('--group23', action='store_true')
    parser.add_argument('--capture', action='store_true', help='send verified external shutter contacts after original readiness')
    parser.add_argument('--duration', type=float)
    parser.add_argument('--full-hold', type=float, default=.5)
    args = parser.parse_args()
    duration = args.duration if args.duration is not None else (40 if args.capture else 2)
    if not 2 <= duration <= 60 or (args.capture and duration < 36):
        parser.error('duration must be 2..60, or 36..60 with capture')
    if args.output.exists():
        raise FileExistsError('Existing evidence is protected')
    host.verify_build(host.DEFAULT_QEMU)
    receipt = {'experimental': True, 'factory_calibration': False,
               'zero_body': True, 'container_marker_hypothesis': 'ENDM',
               'enabled': args.group23, 'address': '0x13420000', 'size': 0xE0000,
               'capture_contacts': args.capture, 'duration': duration, 'full_hold': args.full_hold,
               'probe_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    fixture = None
    if args.group23:
        work = Path(tempfile.mkdtemp(prefix='z62-group23-'))
        if not str(work).isascii() or ',' in str(work):
            raise ValueError('Diagnostic loader requires an ASCII path without commas')
        fixture = work / 'group23.bin'
        data = image()
        with fixture.open('xb') as handle:
            handle.write(data)
        receipt.update(path=str(fixture), sha256=hashlib.sha256(data).hexdigest())
    original = route.host.configure_command
    def configure(command, *a, **kw):
        command = original(command, *a, **kw)
        command = host.configure_command(command, args.capture)
        if fixture:
            command += ['-device', f'loader,file={fixture},addr=0x13420000,force-raw=on']
        return command
    state = {0xC1868490: 48, 0xC1869780: 22, 0xC23E3F24: 64}
    state.update({0xC20A3348 + n * 0x30: 12 for n in (0x0B, 0x47, 0x50)})
    with patch.object(route.host, 'DEFAULT_QEMU', host.DEFAULT_QEMU), \
         patch.object(route.host, 'configure_command', configure):
        points = {0x10239734: 'raw-buffer-descriptor', 0x1026E794: 'capture-component-notice'}
        if args.capture:
            points.update({0x1022C28A: 'capture-full-request',
                           0x1022B630: 'capture-next-state-return',
                           0x1022B702: 'capture-permission-ready-worker',
                           0x1022D1A6: 'capture-enter-state3',
                           0x1022D230: 'capture-enter-state0'})
        result = route.run(args.output, args.card, only_points=points,
                           extra_state=state, extra_hit_hook=context,
                           duration=duration, max_stops=300,
                           wait_for_ready=args.capture,
                           extra_contact_hook=fanout if args.capture else None,
                           full_press_hold=args.full_hold)
    receipt['observation_completed'] = bool(result.get('capture_setup_observed') and
                                            result.get('stop_reason') == 'virtual limit')
    if args.capture:
        receipt['observation_completed'] &= result['shutter_route_observation_completed']
    if fixture:
        receipt['image_unchanged'] = hashlib.sha256(fixture.read_bytes()).hexdigest() == receipt['sha256']
    with (args.output / 'fixture.json').open('x', encoding='utf-8') as handle:
        json.dump(receipt, handle, indent=2)
    print(result['summary'])
    print(receipt)
    raise SystemExit(0 if receipt['observation_completed'] else 1)
