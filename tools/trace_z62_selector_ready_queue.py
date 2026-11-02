"""Observe ready callback enqueue acceptance in its original tail-call frame.

The dispatch frame is 96 bytes; the queue helper frame is 112 bytes. This
explicit -16 SP offset is instruction-derived. The generic queue epilogue is
armed only after this callback's registration point and disarmed on its return.
"""
import argparse
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import trace_z62_selector_route as parent
import trace_z62_capture_queue as queue

VERSION = '2026.11.01-selector-ready-queue-r31'
CALLBACK = 0x10322B51
POINTS = {0x10324622: 'ready-callback-register',
          0x1031627E: 'ready-callback-enqueue-return',
          0x10316288: 'ready-callback-enqueue-frame-end',
          0x10322B50: 'ready-bit2-callback-entry'}
WINDOW = {'entry': 0x10324622, 'return_pc': 0x10316288, 'register': 'r3', 'equals': 0,
          'points': [0x1031627E], 'return_sp_delta': -16, 'gate_return': True}


def run(output, card, group23):
    route = parent.probe.baseline.route
    original_run = route.run

    def framed(*args, **kwargs):
        original_hit = kwargs.get('extra_hit_hook')

        def hit(remote, registers):
            result = original_hit(remote, registers) if original_hit else {}
            if registers['pc'] == 0x1031627E:
                if registers['r4'] == CALLBACK:
                    result['ready_enqueue'] = queue.context(remote, registers)
                else:
                    result['other_enqueue_in_window'] = hex(registers['r4'])
            return result

        kwargs['only_points'] = {**kwargs.get('only_points', {}), **POINTS}
        kwargs['extra_hit_hook'] = hit
        kwargs['breakpoint_window'] = WINDOW
        kwargs['max_stops'] = 750
        return original_run(*args, **kwargs)

    with patch.object(route, 'run', framed):
        receipt = parent.run(output, card, group23)
    trace = json.loads((output / 'trace.json').read_text(encoding='utf-8'))
    enqueues = [{'guest_seconds': row['state']['virtual_seconds'],
                 'accepted': int(row['registers']['r0'], 16),
                 'work_id': row['registers']['r4'], 'sp': row['registers']['sp'],
                 **row['extra_observation']['ready_enqueue']}
                for row in trace['hits'] if 'ready_enqueue' in row.get('extra_observation', {})]
    result = {'schema': 1, 'profile': VERSION,
              'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'completed': bool(receipt['completed'] and not trace.get('breakpoint_window_active', True)),
              'enqueue_observed': bool(enqueues), 'enqueues': enqueues,
              'window': WINDOW, 'window_events': trace.get('breakpoint_window_events', []),
              'ready_callback_hits': sum(row['label'] == 'ready-bit2-callback-entry' for row in trace['hits']),
              'guest_software_written_by_host': False, 'guest_functions_called_by_host': False,
              'mode_recovery_verified': False, 'physical_photo_video_identity_verified': False,
              'camera_accessed': False}
    with (output / 'queue.json').open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2)
    print(json.dumps({'completed': result['completed'], 'ready_enqueues': len(enqueues),
                      'ready_callback_hits': result['ready_callback_hits']}), flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--card', type=Path, required=True)
    parser.add_argument('--group23', type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(0 if run(args.output, args.card, args.group23)['completed'] else 1)
