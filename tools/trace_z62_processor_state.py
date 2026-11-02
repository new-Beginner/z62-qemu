"""Observe original processor state-word writes; never set a ready state."""
import argparse
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import trace_z62_selector_processing as parent
import trace_z62_selector_route as selector

VERSION = '2026.11.02-processor-state-watch-r35b'
ADDRESS = 0xC1864CD0


def extract_writes(trace):
    rows = []
    for hit in trace['hits']:
        if hit.get('watch_address') != hex(ADDRESS):
            continue
        pair = []
        for name in ('watch_before', 'watch_after'):
            value = hit.get(name)
            if not isinstance(value, str):
                raise ValueError('Missing native processor write bytes')
            try:
                data = bytes.fromhex(value)
            except ValueError as exc:
                raise ValueError('Invalid native processor write bytes') from exc
            if len(data) != 4:
                raise ValueError('Incomplete native processor state word')
            pair.append(data)
        before, after = pair
        rows.append({'sequence': hit['sequence'], 'guest_seconds': hit['state']['virtual_seconds'],
                     'thread': hit['thread'], 'pc': hit['registers']['pc'],
                     'registers': hit['registers'], 'instruction_4': hit['watch_instruction_4'],
                     'before': before.hex(), 'after': after.hex(),
                     'before_state': before[1], 'after_state': after[1],
                     'before_mode': before[2], 'after_mode': after[2]})
    return rows


def run(output, card, group23):
    if output.exists():
        raise FileExistsError('Existing evidence is immutable')
    build = parent.hardware.verify_build()
    fixture = selector.probe.baseline
    original_route = fixture.route.run
    original_configure = fixture.host.configure_command

    def configure(command, *args, **kwargs):
        result = original_configure(command, *args, **kwargs)
        return parent.statistics.configure_command(parent.boundary.configure_command(result, True), True)

    def watched(*args, **kwargs):
        kwargs['write_watchpoints'] = {ADDRESS: 4}
        kwargs['breakpoint_window'] = None
        kwargs['max_stops'] = 1000
        return original_route(*args, **kwargs)

    with patch.object(fixture.host, 'configure_command', configure), \
         patch.object(fixture.route, 'run', watched):
        receipt = selector.run(output, card, group23)
    trace = json.loads((output / 'trace.json').read_text(encoding='utf-8'))
    writes = extract_writes(trace)
    result = {'schema': 1, 'profile': VERSION, 'completed_observation': receipt['completed'],
              'qemu_sha256': build['binary_sha256'], 'raw_boundary_requested': True,
              'continuous_statistics_requested': True, 'call_frame_window_enabled': False,
              'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'processor_state_word': hex(ADDRESS), 'native_cpu_writes_observed': bool(writes),
              'writes': writes, 'stop_reason': trace.get('stop_reason'),
              'process_closed': trace.get('process_closed'), 'snapshots_atomic': False,
              'guest_software_written_by_host': False, 'guest_functions_called_by_host': False,
              'hardware_completion_verified': False, 'mode_recovery_verified': False,
              'whole_camera_verified': False, 'camera_accessed': False}
    with (output / 'processor-state.json').open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2)
    print(json.dumps({'completed_observation': result['completed_observation'],
                      'native_cpu_writes': len(writes), 'stop_reason': result['stop_reason']}), flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--card', type=Path, required=True)
    parser.add_argument('--group23', type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(0 if run(args.output, args.card, args.group23)['completed_observation'] else 1)
