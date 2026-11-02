"""Original ISO plus physical encoder observation, without automatic shutters."""
import argparse
import hashlib
import json
from pathlib import Path
import time
from types import SimpleNamespace
from unittest.mock import patch

import trace_z62_capture_setup as trace
import run_z62_raw_stream as raw
import run_z62_finite_stats as finite
import run_z62_preview as preview
import run_z62_capture_contacts as contacts
import z62_shutter_input_v2 as shutter
import z62_capture_input as capture_input
import z62_lens_contact as lens
import z62_qmp_transport as monitor
import z62_encoder_input as encoder
from z62_preview_status import preview_status
from z62_virtual_sd import image_path, digest
from probe_z62_body_inputs import GROUP23_SHA256


def run(output, card, group23):
    card = image_path(card)
    card_before = digest(card)
    fixture = group23.resolve(strict=True)
    if not str(fixture).isascii() or ',' in str(fixture) or hashlib.sha256(fixture.read_bytes()).hexdigest() != GROUP23_SHA256:
        raise ValueError('Expected recorded experimental NOR23')
    contacts.verify_build(contacts.DEFAULT_QEMU)
    original_configure, original_apply = raw.configure_command, trace.host.host.apply_console
    original_observe = trace.trace.observe_capture
    events, frames = [], []
    started = None
    cursor = 0
    next_time = None
    plan = [('frame', 'before'), ('key', 0)]
    plan += [('phase', 0, phase) for phase in encoder.ENCODERS[0]['negative']]
    plan += [('key', 1), ('frame', 'after-encoder0'), ('key', 0)]
    plan += [('phase', 1, phase) for phase in encoder.ENCODERS[1]['positive']]
    plan += [('key', 1), ('frame', 'after-encoder1')]

    def configure(command, *args, **kwargs):
        result = preview.configure_command(finite.configure_command(original_configure(command, *args, **kwargs)), True)
        result = contacts.configure_command(result, True)
        return result + ['-device', f'loader,file={fixture},addr=0x13420000,force-raw=on']

    def apply(source, persistent=False):
        original_apply(source, persistent)
        shutter.apply_console(source)
        lens.apply_console(source)
        capture_input.apply_console(source)
        encoder.apply_console(source)
        monitor.apply_console(source)

    def capture(machine):
        return {**original_observe(machine), **preview_status(machine)}

    def hit(remote, registers):
        pointer = registers['r0']
        if registers['pc'] != 0x10436600 or not 0xC0000000 <= pointer <= 0xDFFFFF80:
            raise ValueError('Unexpected original decoder entry')
        payload = remote.read(pointer, 124)
        return {'encoder_payload': payload.hex(), 'iso_byte': payload[0x16],
                'encoder_counts': [int.from_bytes(payload[offset:offset+1], 'little', signed=True)
                                   for offset in (0x0B, 0x0C)]}

    def observe(machine, row):
        nonlocal started, cursor, next_time
        with machine.io:
            # Keep real held input alive; the inherited wall-clock watchdog
            # otherwise releases it before a slow virtual-clock interval ends.
            if machine.requested_keys:
                machine.key_deadline = time.monotonic() + 5
            ready = machine._words(0xC1821EB8, 1)[0]
            joined = machine._words(0xC1868AE8, 1)[0]
            words = machine._words(0xC25D6FC0, 8)
        row['encoder_combo_state'] = {'inhibit': ready, 'joined': joined,
                                      'input_words': [hex(word) for word in words]}
        now = row['virtual_seconds']
        if started is None:
            if now < 30 or row['index'] != 3 or ready != 0 or joined != 3:
                return None
            started, next_time = now, now
        if cursor == len(plan) or now < next_time:
            return None
        item = plan[cursor]
        if item[0] == 'frame':
            data = machine.frame_png()
            filename = item[1] + '.png'
            with (output / filename).open('xb') as handle:
                handle.write(data)
            frames.append({'file': filename, 'sha256': hashlib.sha256(data).hexdigest(), 'virtual_seconds': now})
            delay = .3
        elif item[0] == 'key':
            with machine.io:
                machine._set_key_locked(19, item[1])
            delay = .4 if item[1] == 0 else 4.0
        else:
            with machine.io:
                encoder.drive_phase(machine, item[1], item[2])
            delay = .2
        event = {'virtual_seconds': now, 'operation': item, 'sequence': cursor}
        events.append(event)
        print('ENCODER_COMBO', json.dumps(event), flush=True)
        cursor += 1
        next_time = now + delay
        return event

    args = SimpleNamespace(output=output, qemu=contacts.DEFAULT_QEMU, native_source=True,
        input_drain=True, frame_start=True, boundary_experiment=False, boundary_line=136,
        ready_bit_experiment=False, ready_set_experiment=False, lifecycle=False, frame_objects=False,
        ownership=False, metadata_event_experiment=False, startup_waits=False,
        virtual_limit=49, wall_limit=1500, menu_at=1000, reopen_delay=1000,
        poll=2, max_stops=300, sd_card=card, breakpoint_window=None,
        write_watchpoints=None, read_watchpoints=None)
    with patch.object(raw, 'configure_command', configure), \
         patch.object(trace.host.host, 'apply_console', apply), \
         patch.object(trace.trace, 'observe_capture', capture), \
         patch.object(trace, 'POINTS', {0x10436600: 'encoder-message'}), \
         patch.object(trace, 'STATE', {0xC1821EB8: 1, 0xC1868AE8: 1, 0xC25D6FC0: 8}):
        result = trace.run(args, extra_hit_hook=hit, extra_observation_hook=observe)
    receipt = {'schema': 1, 'events': events, 'frames': frames, 'original_ready_at': started,
               'encoder_adapter': encoder.identity(),
               'completed': bool(len(events) == len(plan) and len(frames) == 3 and
                    result.get('process_closed') and result.get('detach') == 'OK' and
                    result.get('stop_reason') == 'virtual limit' and not result.get('failure')),
               'virtual_card': {'snapshot': True, 'before_sha256': card_before, 'after_sha256': digest(card)},
               'automatic_shutter_events': [], 'guest_software_patched': False}
    with (output / 'combo.json').open('x', encoding='utf-8') as handle:
        json.dump(receipt, handle, indent=2)
    print(json.dumps(receipt, indent=2))
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--card', type=Path, required=True)
    parser.add_argument('--group23', type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(0 if run(args.output, args.card, args.group23)['completed'] else 1)
