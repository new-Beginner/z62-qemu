"""Observe the real enqueue return inside the original capture submission call.

Uses a call-frame breakpoint window to avoid high-volume unrelated enqueues.
Reads queue occupancy and work IDs; never increases capacity or drops work.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
from unittest.mock import patch

import probe_z62_no_lens as fixture
from probe_z62_no_lens import run

POINTS = {
    0x10325186: 'capture-submit-entry',
    0x1031627E: 'capture-enqueue-return',
    0x103EC564: 'capture-submit-return',
    0x10320018: 'capture-queued-worker',
}
WINDOW = {'entry': 0x10325186, 'return_pc': 0x103EC564, 'register': 'r1',
          'equals': 0x103EAE81, 'points': [0x1031627E]}


def context(remote, registers):
    if registers['pc'] not in POINTS:
        return {}
    raw = remote.read(0xC23D9F14, 24)
    words = [int.from_bytes(raw[i:i+4], 'little') for i in range(0, 24, 4)]
    base, stride, capacity, count, head, mutex = words
    stride &= 255
    if (stride != 92 or not 1 <= capacity <= 256 or not 0 <= count <= capacity or
            not 0 <= head < capacity or not 0xC0000000 <= base <= 0xE0000000-stride*capacity):
        raise ValueError('Queue layout does not match the original bounded contract')
    entries = remote.read(base, stride*capacity)
    tasks = [hex(int.from_bytes(entries[((head+i) % capacity)*stride:((head+i) % capacity)*stride+4],
                                'little')) for i in range(count)]
    return {'queue_header_24': raw.hex(), 'capacity': capacity, 'count': count, 'head': head,
            'work_ids_in_order': tasks, 'work_id_counts': dict(Counter(tasks))}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--card', type=Path, required=True)
    parser.add_argument('--group23', type=Path, required=True)
    parser.add_argument('--native-boundary', action='store_true')
    args = parser.parse_args()
    def execute():
        return run(args.output, args.card, args.group23, True, True, 36,
                   extra_points=POINTS, extra_state={0xC23D9F14: 6},
                   extra_hit_hook=context, breakpoint_window=WINDOW)
    native = None
    if args.native_boundary:
        import run_z62_raw_boundary as native_host
        native = native_host.verify_build(native_host.DEFAULT_QEMU)
        original_configure = fixture.host.configure_command
        def configure(command, *a, **kw):
            return native_host.configure_command(original_configure(command, *a, **kw))
        with patch.object(fixture.host, 'DEFAULT_QEMU', native_host.DEFAULT_QEMU), \
             patch.object(fixture.host, 'configure_command', configure):
            result, receipt = execute()
    else:
        result, receipt = execute()
    hits = [h for h in result['hits'] if h['label'] == 'capture-enqueue-return']
    completed = receipt['observation_completed'] and not result.get('breakpoint_window_active', True)
    summary = {'observation_completed': completed,
               'native_boundary_identity': native['raw_boundary_device'] if native else None,
               'enqueue_returns': [{'virtual_seconds': h['state']['virtual_seconds'],
                                    'accepted': int(h['registers']['r0'], 16),
                                    'work_id': h['registers']['r4'],
                                    'callback': h['registers']['r7'],
                                    **h['extra_observation']} for h in hits],
               'capture_worker_hits': sum(h['label'] == 'capture-queued-worker' for h in result['hits']),
               'photo_capture_verified': False, 'complete_emulator': False}
    with (args.output / 'queue-analysis.json').open('x', encoding='utf-8') as handle:
        json.dump(summary, handle, indent=2)
    print(json.dumps(summary, indent=2))
    raise SystemExit(0 if completed and hits else 1)
