"""Observe one physical expander input on the frozen r13/r16 camera profile.

Unknown pins remain hypotheses. This probe records original switch words and
LCD frames; it never writes guest RAM, calls guest functions, or labels a pin
from another camera's table. Run each observation in a separate Python process.
"""
import argparse
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import probe_z62_liveview as base
import probe_z62_preview_firmware as preview
import run_z62_capture_contacts as contacts
import z62_shutter_input_v2 as shutter
import z62_capture_input as capture
import z62_lens_contact as lens
import z62_qmp_transport as monitor

GROUP23_SHA256 = 'c7dd14358b45b2813fdee85fc587bcdd5899f7a81e0d5830513d631235bcc700'


def run(output, group23, pin, *, duration=47, wall_limit=1200):
    if type(pin) is not int or not 0 <= pin < 24:
        raise ValueError('Expected one expander pin in 0..23')
    fixture = group23.resolve(strict=True)
    if (not str(fixture).isascii() or ',' in str(fixture) or
            hashlib.sha256(fixture.read_bytes()).hexdigest() != GROUP23_SHA256):
        raise ValueError('Expected the recorded experimental NOR23 fixture')
    contacts.verify_build(contacts.DEFAULT_QEMU)
    original_apply = base.host.host.apply_console
    original_configure = preview.host.configure_command
    original_observe = base.observe_capture
    events = []
    phase = 0
    last_event = 0

    def apply(source, *args, **kwargs):
        original_apply(source, *args, **kwargs)
        shutter.apply_console(source)
        lens.apply_console(source)
        capture.apply_console(source)
        monitor.apply_console(source)

    def configure(command, *args, **kwargs):
        result = contacts.configure_command(original_configure(command, *args, **kwargs), True)
        return result + ['-device', f'loader,file={fixture},addr=0x13420000,force-raw=on']

    def observe(machine):
        nonlocal phase, last_event
        result = original_observe(machine)
        ticks, frequency = machine._key_clock()
        now = ticks / frequency
        words = [hex(word) for word in machine._words(0xC25D6FC0, 3)]
        result['body_input_probe'] = {'virtual_seconds': now, 'switch_words': words,
                                      'phase_before_action': phase}
        action = None
        if phase == 0 and now >= 25:
            action = (pin, 0, 'candidate-press')
        elif phase == 1 and now - last_event >= 1:
            action = (pin, 1, 'candidate-release')
        elif phase == 2 and now - last_event >= 10:
            action = (capture.HALF_PRESS, 0, 'half-press-return')
        elif phase == 3 and now - last_event >= 1:
            action = (capture.HALF_PRESS, 1, 'half-release')
        if action:
            key, level, label = action
            machine._set_key_locked(key, level)
            event = {'pin': key, 'level': level, 'action': label,
                     'virtual_seconds': now, 'switch_words_before': words}
            events.append(event)
            print('BODY_INPUT', json.dumps(event), flush=True)
            phase += 1
            last_event = now
        return result

    with patch.object(preview.host, 'DEFAULT_QEMU', contacts.DEFAULT_QEMU), \
         patch.object(preview.host, 'configure_command', configure), \
         patch.object(base.host.host, 'apply_console', apply), \
         patch.object(base, 'observe_capture', observe):
        result = preview.run(output, duration, wall_limit)
    result['body_input_probe'] = {
        'schema': 1, 'pin': pin, 'events': events,
        'observation_completed': bool(result.get('observation_completed') and len(events) == 4),
        'physical_button_identity_verified': False,
        'input_adapter': capture.identity(), 'lens_contact': lens.identity(),
        'group23_sha256': GROUP23_SHA256,
        'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    (output / 'report.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--group23', type=Path, required=True)
    parser.add_argument('--pin', type=int, choices=range(24), required=True)
    parser.add_argument('--duration', type=float, default=47)
    parser.add_argument('--wall-limit', type=float, default=1200)
    args = parser.parse_args()
    if not 43 <= args.duration <= 65 or not 60 <= args.wall_limit <= 1800:
        parser.error('duration 43..65 and wall-limit 60..1800 required')
    result = run(args.output, args.group23, args.pin,
                 duration=args.duration, wall_limit=args.wall_limit)
    print(json.dumps(result['body_input_probe'], indent=2))
    raise SystemExit(0 if result['body_input_probe']['observation_completed'] else 1)
