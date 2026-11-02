"""Trace original selector propagation and APPLV consumption using the r28 plan.

The original sustained GPIO sequence is preserved. Additional read-only stops
distinguish wire reception, cached input, comparison and application delivery.
"""
import argparse
import json
from pathlib import Path
from unittest.mock import patch

import trace_z62_photo_video_selector as probe
import z62_selector_observation as observation


def run(output, card, group23):
    original_run = probe.baseline.run

    def traced(*args, **kwargs):
        original_hit = kwargs.get('extra_hit_hook')

        def hit(remote, registers):
            result = original_hit(remote, registers) if original_hit else {}
            if registers['pc'] in observation.POINTS:
                result['selector_route'] = observation.capture(remote, registers)
            return result

        kwargs['extra_points'] = {**observation.POINTS, **kwargs.get('extra_points', {})}
        kwargs['extra_hit_hook'] = hit
        kwargs['max_stops'] = 500
        return original_run(*args, **kwargs)

    with patch.object(probe.baseline, 'run', traced):
        receipt = probe.run(output, card, group23)
    record = json.loads((output / 'trace.json').read_text(encoding='utf-8'))
    observed = [{'label': row['label'], 'virtual_seconds': row['state']['virtual_seconds'],
                 **row['extra_observation']['selector_route']}
                for row in record['hits'] if 'selector_route' in row.get('extra_observation', {})]
    result = {'schema': 1, 'profile': observation.VERSION, 'observation': observation.identity(),
              'completed': receipt['completed'], 'hits': observed, 'qemu_sha256': receipt['qemu_sha256'],
              'physical_photo_video_identity_verified': False, 'mode_recovery_verified': False,
              'guest_memory_written': False, 'guest_functions_called': False,
              'camera_accessed': False}
    with (output / 'route.json').open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2)
    print(json.dumps({'completed': result['completed'], 'route_hits': len(observed)}), flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--card', type=Path, required=True)
    parser.add_argument('--group23', type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(0 if run(args.output, args.card, args.group23)['completed'] else 1)
