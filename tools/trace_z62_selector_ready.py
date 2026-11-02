"""Observe original ready-word CPU writes and the bit2 callback during r29 input.

Uses the existing native GDB write watchpoint/single-step support. No host write
to the ready word, no guest callback invocation and no completion injection.
"""
import argparse
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import trace_z62_selector_route as parent

VERSION = '2026.11.01-selector-ready-watch-r30'
READY = 0xC1868AE8
CALLBACK = 0x10322B50


def run(output, card, group23):
    route = parent.probe.baseline.route
    original_run = route.run

    def watched(*args, **kwargs):
        kwargs['write_watchpoints'] = {READY: 4}
        kwargs['only_points'] = {**kwargs.get('only_points', {}), CALLBACK: 'ready-bit2-callback-entry'}
        kwargs['max_stops'] = 2500
        return original_run(*args, **kwargs)

    with patch.object(route, 'run', watched):
        receipt = parent.run(output, card, group23)
    trace = json.loads((output / 'trace.json').read_text(encoding='utf-8'))
    writes = [{'guest_seconds': row['state']['virtual_seconds'],
               'pc': row['registers']['pc'], 'lr': row['registers']['lr'], 'thread': row['thread'],
               'before': row['watch_before'], 'after': row.get('watch_after'),
               'instruction_4': row['watch_instruction_4'], 'registers': row['registers']}
              for row in trace['hits'] if row.get('watch_address') == hex(READY)]
    callbacks = [{'guest_seconds': row['state']['virtual_seconds'], 'registers': row['registers']}
                 for row in trace['hits'] if row['label'] == 'ready-bit2-callback-entry']
    result = {'schema': 1, 'profile': VERSION, 'completed': receipt['completed'],
              'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'ready_word': hex(READY), 'writes': writes, 'callbacks': callbacks,
              'guest_software_written_by_host': False, 'guest_functions_called_by_host': False,
              'mode_recovery_verified': False, 'physical_photo_video_identity_verified': False,
              'camera_accessed': False}
    with (output / 'ready.json').open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2)
    print(json.dumps({'completed': result['completed'], 'ready_cpu_writes': len(writes),
                      'ready_callbacks': len(callbacks)}), flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--card', type=Path, required=True)
    parser.add_argument('--group23', type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(0 if run(args.output, args.card, args.group23)['completed'] else 1)
