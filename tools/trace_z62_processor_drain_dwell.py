"""Continue the original-clock drain observation beyond the existing backlog.

The sustained input plan and device configuration stay unchanged. A fresh final
RAM snapshot and LCD frame distinguish a slow natural drain from a short timeout.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
from unittest.mock import patch

import trace_z62_processor_drain as parent

VERSION = '2026.11.02-processor-drain-dwell-r36b2'


def validate_duration(value):
    if type(value) not in (int, float) or not math.isfinite(value) or not 60 <= value <= 180:
        raise ValueError('Long observation requires 60..180 finite guest seconds')
    return float(value)


def run(output, card, group23, duration=150):
    duration = validate_duration(duration)
    if output.exists():
        raise FileExistsError('Existing evidence is immutable')
    fixture = parent.selector.probe.baseline
    original_route = fixture.route.run
    final_frame = None

    def extended(*args, **kwargs):
        original_observe = kwargs.get('extra_observation_hook')

        def observe(machine, row):
            nonlocal final_frame
            event = original_observe(machine, row) if original_observe else None
            if final_frame is None and row['virtual_seconds'] >= duration-1:
                class Reader:
                    def read(self, address, size):
                        words = machine._words(address, size//4)
                        if len(words) != size//4 or any(type(v) is not int or not 0 <= v <= 0xFFFFFFFF for v in words):
                            raise ValueError('Incomplete final QMP RAM observation')
                        return struct.pack('<'+'I'*len(words), *words)
                with machine.io:
                    state = parent.snapshot(Reader())
                data = machine.frame_png()
                with (output / 'dwell-final.png').open('xb') as handle:
                    handle.write(data)
                final_frame = {'file': 'dwell-final.png', 'sha256': hashlib.sha256(data).hexdigest(),
                               'guest_seconds_before_read': row['virtual_seconds'],
                               'display_enabled': row['display_enabled'], 'snapshot': state}
                print('DWELL_FINAL_FRAME', row['virtual_seconds'], row['display_enabled'],
                      state['state'], state['pending_stop'], flush=True)
            return event

        kwargs.update(duration=duration, wall_limit=3600, max_stops=2000,
                      extra_observation_hook=observe)
        return original_route(*args, **kwargs)

    with patch.object(fixture.route, 'run', extended):
        receipt = parent.run(output, card, group23)
    trace = json.loads((output / 'trace.json').read_text(encoding='utf-8'))
    last = trace['observations'][-1]
    result = {'schema': 1, 'profile': VERSION, 'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'target_guest_seconds': duration, 'actual_guest_seconds': last['virtual_seconds'],
              'completed_observation': bool(receipt['completed_observation'] and final_frame is not None and
                                            last['virtual_seconds'] >= duration),
              'final_frame': final_frame, 'final_display_enabled': last.get('display_enabled'),
              'final_ready_join': last['extra_words']['0xc1868ae8'][0],
              'stop_reason': trace.get('stop_reason'), 'process_closed': trace.get('process_closed'),
              'original_clock_shift_changed': False, 'guest_software_written_by_host': False,
              'guest_functions_called_by_host': False, 'software_event_injected': False,
              'mode_recovery_verified': False, 'whole_camera_verified': False,
              'factory_af_verified': False, 'camera_accessed': False}
    with (output / 'dwell.json').open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2)
    print(json.dumps({k: result[k] for k in ('completed_observation', 'actual_guest_seconds',
                      'final_display_enabled', 'final_ready_join', 'stop_reason')}), flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--card', type=Path, required=True)
    parser.add_argument('--group23', type=Path, required=True)
    parser.add_argument('--duration', type=float, default=150)
    args = parser.parse_args()
    raise SystemExit(0 if run(args.output, args.card, args.group23, args.duration)['completed_observation'] else 1)
