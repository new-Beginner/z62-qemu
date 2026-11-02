"""Observe native writes to one pending-list count and bounded stack bytes.

The stack is raw evidence, not an automatically reconstructed call chain. The
observer never changes the count, frame flags, guest registers or responses.
"""
import argparse
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import trace_z62_selector_processing as profiles
import trace_z62_selector_route as selector

VERSION = '2026.11.02-processor-retire-count-r37'
ADDRESS = 0xC237A8BC


def stack_context(remote, registers):
    stack = registers.get('sp')
    available = type(stack) is int and stack % 4 == 0 and 0xC0000000 <= stack <= 0xE0000000-96
    result = {'available': available, 'address': hex(stack) if type(stack) is int else None}
    if available:
        data = remote.read(stack, 96)
        if not isinstance(data, bytes) or len(data) != 96:
            raise ValueError('Incomplete native retirement stack context')
        result['raw_60'] = data.hex()
    return result


def extract_writes(trace):
    rows = []
    for hit in trace['hits']:
        if hit.get('watch_address') != hex(ADDRESS):
            continue
        values = []
        for field in ('watch_before', 'watch_after'):
            raw = hit.get(field)
            if not isinstance(raw, str):
                raise ValueError('Missing native queue-count write evidence')
            try:
                data = bytes.fromhex(raw)
            except ValueError as exc:
                raise ValueError('Invalid native queue-count bytes') from exc
            if len(data) != 4:
                raise ValueError('Incomplete native queue-count word')
            values.append(int.from_bytes(data, 'little'))
        before, after = values
        rows.append({'sequence': hit['sequence'], 'guest_seconds': hit['state']['virtual_seconds'],
                     'thread': hit['thread'], 'pc': hit['registers']['pc'],
                     'registers': hit['registers'], 'instruction_4': hit['watch_instruction_4'],
                     'before_count': before, 'after_count': after, 'delta': after-before,
                     'stack_context': hit.get('extra_observation', {}).get('retire_stack')})
    return rows


def run(output, card, group23):
    if output.exists():
        raise FileExistsError('Existing evidence is immutable')
    build = profiles.hardware.verify_build()
    fixture = selector.probe.baseline
    original_configure = fixture.host.configure_command
    original_route = fixture.route.run

    def configure(command, *args, **kwargs):
        result = original_configure(command, *args, **kwargs)
        return profiles.statistics.configure_command(profiles.boundary.configure_command(result, True), True)

    def observed(*args, **kwargs):
        original_hit = kwargs.get('extra_hit_hook')

        def hit(remote, registers):
            result = original_hit(remote, registers) if original_hit else {}
            result['retire_stack'] = stack_context(remote, registers)
            return result

        kwargs.update(write_watchpoints={ADDRESS: 4}, breakpoint_window=None,
                      max_stops=2500, extra_hit_hook=hit,
                      extra_state={**kwargs.get('extra_state', {}), 0xC1864CD0: 2, 0xC237A8B4: 8})
        return original_route(*args, **kwargs)

    with patch.object(fixture.host, 'configure_command', configure), \
         patch.object(fixture.route, 'run', observed):
        receipt = selector.run(output, card, group23)
    trace = json.loads((output / 'trace.json').read_text(encoding='utf-8'))
    writes = extract_writes(trace)
    result = {'schema': 1, 'profile': VERSION, 'completed_observation': receipt['completed'],
              'qemu_sha256': build['binary_sha256'], 'count_address': hex(ADDRESS),
              'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'writes': writes, 'cpu_threads': sorted({w['thread'] for w in writes}),
              'stop_reason': trace.get('stop_reason'), 'process_closed': trace.get('process_closed'),
              'stack_call_chains_verified': False, 'retirement_wait_reason_verified': False,
              'raw_boundary_requested': True, 'continuous_statistics_requested': True,
              'guest_software_written_by_host': False, 'guest_functions_called_by_host': False,
              'software_event_injected': False, 'mode_recovery_verified': False,
              'whole_camera_verified': False, 'camera_accessed': False}
    with (output / 'retire-count.json').open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2)
    print(json.dumps({'completed_observation': result['completed_observation'],
                      'native_count_writes': len(writes), 'stop_reason': result['stop_reason']}), flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--card', type=Path, required=True)
    parser.add_argument('--group23', type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(0 if run(args.output, args.card, args.group23)['completed_observation'] else 1)
