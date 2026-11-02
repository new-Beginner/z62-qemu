"""Observe original configuration call/return and control-state update, read-only.

Uses the explicit r32 data-backed processing profile. A returned operation code
is not an acknowledgement. Requested buffers are read only before application;
they may have been released when the original function returns.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
from unittest.mock import patch

import trace_z62_selector_processing as parent

VERSION = '2026.11.01-selector-configuration-observation-r33'
POINTS = {0x103226AE: 'configuration-apply-call',
          0x103226B2: 'configuration-apply-return',
          0x103226BA: 'configuration-control-updated'}


def capture(remote, registers):
    pc = registers.get('pc')
    if type(pc) is not int or pc not in POINTS:
        raise ValueError('Not an original configuration observation point')

    def read(address, size):
        data = remote.read(address, size)
        if not isinstance(data, bytes) or len(data) != size:
            raise ValueError('Incomplete configuration snapshot')
        return data

    def header(pointer, size):
        available = type(pointer) is int and 0xC0000000 <= pointer <= 0xE0000000-size
        result = {'pointer': hex(pointer) if type(pointer) is int else None, 'available': available}
        if available:
            data = read(pointer, size)
            result.update(raw=data.hex(), byte_00=data[0])
            if size == 32:
                result['byte_18'] = data[0x18]
            else:
                result['flags_0c'] = data[0xC]
        return result

    context = read(0xC1868A70, 144)
    current, operation = struct.unpack_from('<II', context, 0x88)
    result = {'stage': POINTS[pc], 'context_90': context.hex(),
              'byte_01': context[1], 'byte_03': context[3],
              'ready_join': struct.unpack_from('<I', context, 0x78)[0],
              'current': header(current, 32), 'active_operation': header(operation, 16),
              'read_only': True}
    if pc == 0x103226AE:
        result['argument'] = header(registers['r0'], 32)
    elif pc == 0x103226B2:
        result['returned_control_code'] = registers['r0']
    else:
        result['r0_after_control_update'] = registers['r0']
    return result


def run(output, card, group23):
    if output.exists():
        raise FileExistsError('Existing evidence is immutable')
    fixture = parent.parent.parent.probe.baseline
    original_route = fixture.route.run

    def instrumented(*args, **kwargs):
        original_hit = kwargs.get('extra_hit_hook')

        def hit(remote, registers):
            result = original_hit(remote, registers) if original_hit else {}
            if registers['pc'] in POINTS:
                result['configuration'] = capture(remote, registers)
            return result

        kwargs['only_points'] = {**kwargs.get('only_points', {}), **POINTS}
        kwargs['extra_hit_hook'] = hit
        kwargs['max_stops'] = 1200
        return original_route(*args, **kwargs)

    with patch.object(fixture.route, 'run', instrumented):
        receipt = parent.run(output, card, group23, enabled=True)
    trace_path = output / 'trace.json'
    trace = json.loads(trace_path.read_text(encoding='utf-8')) if trace_path.exists() else {}
    rows = [{'guest_seconds': row['state']['virtual_seconds'], 'registers': row['registers'],
             **row['extra_observation']['configuration']}
            for row in trace.get('hits', []) if 'configuration' in row.get('extra_observation', {})]
    result = {'schema': 1, 'profile': VERSION, 'completed': receipt['completed'],
              'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'snapshots': rows, 'configuration_observed': bool(rows),
              'guest_software_written_by_host': False, 'guest_functions_called_by_host': False,
              'mode_recovery_verified': False, 'physical_photo_video_identity_verified': False,
              'camera_accessed': False}
    with (output / 'configuration.json').open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2)
    print(json.dumps({'completed': result['completed'], 'configuration_snapshots': len(rows)}), flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--card', type=Path, required=True)
    parser.add_argument('--group23', type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(0 if run(args.output, args.card, args.group23)['completed'] else 1)
