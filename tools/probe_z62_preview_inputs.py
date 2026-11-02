"""Compare actual external key routes on frozen r9; never patch guest software.

GPIO identities are hypotheses until the original decoder's switch word confirms
them. Each run uses a fresh process and keeps the existing r9 evidence intact.
"""
import argparse
import hashlib
import json
from pathlib import Path

import probe_z62_liveview as base
import probe_z62_preview_firmware as preview


def run(output, route, pin, duration=45, hold=1.0):
    original = base.observe_capture
    events = []
    phase = 0
    started = None

    def observe(machine):
        nonlocal phase, started
        capture = original(machine)
        ticks, frequency = machine._key_clock()
        now = ticks / frequency
        words = machine._words(0xC25D6FC0, 3)
        capture['input_route_probe'] = {
            'virtual_seconds': now, 'switch_words': [hex(w) for w in words],
            'route': route, 'pin': pin, 'phase_before_action': phase,
        }
        event = None
        if phase == 0 and now >= 20:
            machine._set_key_locked(9, 0)
            machine._set_key_locked(9, 1)
            event = {'action': 'menu-tap', 'pin': 9}
            phase = 1
        elif phase == 1 and now >= 28:
            if route == 'gpio-g':
                machine._qtest(f'set_irq_in /machine/controller/keys-gpio unnamed-gpio-in {pin} 0')
            else:
                machine._set_key_locked(pin, 0)
            event = {'action': 'press', 'route': route, 'pin': pin, 'level': 0}
            started = now
            phase = 2
        elif phase == 2 and now >= started + hold:
            if route == 'gpio-g':
                machine._qtest(f'set_irq_in /machine/controller/keys-gpio unnamed-gpio-in {pin} 1')
            else:
                machine._set_key_locked(pin, 1)
            event = {'action': 'release', 'route': route, 'pin': pin, 'level': 1}
            phase = 3
        if event:
            event.update(virtual_seconds=now, switch_words_before=[hex(w) for w in words])
            events.append(event)
            print('EXTERNAL_INPUT', json.dumps(event), flush=True)
        return capture

    base.observe_capture = observe
    try:
        result = preview.run(output, duration, 900)
    finally:
        base.observe_capture = original
    result['external_input_probe'] = {
        'route': route, 'pin': pin, 'hold_seconds': hold, 'events': events,
        'physical_button_identity_verified': False,
        'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    (output / 'report.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--route', choices=('gpio-g', 'expander'), required=True)
    p.add_argument('--pin', type=int, required=True)
    p.add_argument('--duration', type=float, default=45)
    p.add_argument('--hold', type=float, default=1.0)
    args = p.parse_args()
    if not 35 <= args.duration <= 60 or not .2 <= args.hold <= 5:
        p.error('duration 35..60 and hold .2..5 required')
    if args.pin not in ((14, 15) if args.route == 'gpio-g' else (0, 9)):
        p.error('Only the documented comparison inputs are allowed')
    r = run(args.output, args.route, args.pin, args.duration, args.hold)
    ok = r['observation_completed'] and len(r['external_input_probe']['events']) == 3
    print('input_observation_completed=', ok)
    raise SystemExit(0 if ok else 1)
