"""Observe original C1.70 input messages for four physical Gray-code cycles."""
import argparse
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import probe_z62_no_lens as baseline
import z62_encoder_input as encoder
import z62_encoder_queue as queue
import z62_capture_input as capture
import z62_body_controls as body


def run(output, card, group23, *, queued=False, cancel=False):
    if cancel and not queued:
        raise ValueError('Cancellation observation requires the queued adapter')
    original_apply = baseline.route.shutter.apply_console
    events = []
    steps = [(index, direction, phase) for index, direction in
             ((0, 'positive'), (0, 'negative'), (1, 'positive'), (1, 'negative'))
             for phase in encoder.ENCODERS[index][direction]]
    cursor = 0
    next_time = 2.0
    topology = None

    def apply(source):
        original_apply(source)
        if queued:
            capture.apply_console(source)
            body.apply_console(source)
            queue.apply_console(source)
        else:
            encoder.apply_console(source)

    def observe(machine, row):
        nonlocal cursor, next_time, topology
        if topology is None:
            topology = machine._encoder_ports
        now = row['virtual_seconds']
        if cursor >= len(steps) or now < next_time:
            return None
        index, direction, phase = steps[cursor]
        if queued:
            # rotate owns the non-reentrant Machine.io lock itself.
            machine.rotate(index, 1 if direction == 'positive' else -1)
            if cancel:
                machine.release()
        else:
            with machine.io:
                encoder.drive_phase(machine, index, phase)
        event = {'encoder': index, 'direction': direction, 'phase': phase,
                 'virtual_seconds': now, 'sequence_index': cursor}
        if queued:
            event.pop('phase')
            event['queued_rotation_request'] = True
            event['cancel_after_first_phase'] = cancel
        events.append(event)
        cursor += 4 if queued else 1
        next_time = now + (1 if queued else (.5 if phase == 0 else .2))
        print('ENCODER_PHASE', json.dumps(event), flush=True)
        return event

    def hit(remote, registers):
        if registers['pc'] != 0x10436600:
            return {}
        address = registers['r0']
        if not 0xC0000000 <= address <= 0xDFFFFF80:
            raise ValueError('Original decoder payload is outside RAM')
        payload = remote.read(address, 124)
        return {'encoder_payload': payload.hex(),
                'encoder_counts': [int.from_bytes(payload[offset:offset+1], 'little', signed=True)
                                   for offset in (0x0B, 0x0C)],
                'source': 'original-controller-message-before-master-decoder'}

    with patch.object(baseline.route.shutter, 'apply_console', apply):
        result, fixture = baseline.run(output, card, group23, True, False, 10,
            extra_points={0x10436600: 'encoder-message'}, extra_hit_hook=hit,
            extra_observation_hook=observe, max_stops=300)
    receipt = {'schema': 1, 'encoder_adapter': encoder.identity(), 'events': events,
               'ports': topology, 'scheduled_phase_count': len(steps),
               'queued': queued, 'queue_adapter': queue.identity() if queued else None,
               'cancel_after_first_phase': cancel,
               'completed': bool(fixture['observation_completed'] and cursor == len(steps)
                                 and result.get('process_closed') and not result.get('failure')),
               'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               'photographic_function_verified': False}
    with (output / 'encoder.json').open('x', encoding='utf-8') as handle:
        json.dump(receipt, handle, indent=2)
    return result, receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--card', type=Path, required=True)
    parser.add_argument('--group23', type=Path, required=True)
    parser.add_argument('--queued', action='store_true')
    parser.add_argument('--cancel', action='store_true')
    args = parser.parse_args()
    result, receipt = run(args.output, args.card, args.group23, queued=args.queued, cancel=args.cancel)
    print(receipt)
    raise SystemExit(0 if receipt['completed'] else 1)
