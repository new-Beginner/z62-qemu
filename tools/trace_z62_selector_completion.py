"""Observe original control-code16 preconditions, without completing the work.

The alternate constructor site does not establish an R4 operation-object type.
All returns remain integer observations, never device acknowledgements.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
from unittest.mock import patch

import trace_z62_selector_processing as parent

VERSION = '2026.11.02-selector-completion-gates-r34'
POINTS = {0x1032448C: 'completion-gate-entry',
          0x10324498: 'completion-mode-predicate-return',
          0x103244BE: 'completion-processor-return',
          0x103244CE: 'completion-dispatch-code16',
          0x1032286E: 'completion-constructor-code16',
          0x103D34B4: 'completion-processor-prefix-reject'}
ANCHORS = {0x1032448C: 'b8f1000f', 0x10324498: '0028',
           0x103244BE: '40b1', 0x103244CE: 'fbf7cbb8',
           0x1032286E: 'fcf7fbfe', 0x103D34B4: '0025'}


def capture(remote, registers):
    pc = registers.get('pc')
    if type(pc) is not int or pc not in POINTS:
        raise ValueError('Not an original operation-completion observation point')

    def read(address, size):
        data = remote.read(address, size)
        if not isinstance(data, bytes) or len(data) != size:
            raise ValueError('Incomplete operation-completion snapshot')
        return data

    def available(pointer, size):
        return type(pointer) is int and 0xC0000000 <= pointer <= 0xE0000000-size

    context = read(0xC1868A70, 144)
    state = read(0xC1864CD0, 4)
    result = {'stage': POINTS[pc], 'read_only': True, 'snapshots_atomic': False,
              'context': {'raw': context.hex(), 'state': context[1], 'last_mode': context[5],
                          'ready_join': struct.unpack_from('<I', context, 0x78)[0],
                          'current': hex(struct.unpack_from('<I', context, 0x88)[0]),
                          'active_operation': hex(struct.unpack_from('<I', context, 0x8C)[0])},
              'processor_state': {'raw': state.hex(), 'byte_01': state[1], 'byte_02': state[2]},
              'pending_count_i32': struct.unpack('<i', read(0xC23DC970, 4))[0]}
    if pc == 0x1032448C:
        result['entry_r8'] = registers['r8']
    if pc in (0x10324498, 0x103244BE):
        result['returned_value'] = registers['r0']
    if pc in (0x103244CE, 0x1032286E):
        result['outgoing_control_code'] = registers['r0']
    if pc != 0x1032286E:
        pointer = registers['r4']
        operation = {'pointer': hex(pointer), 'available': available(pointer, 0x148)}
        result['operation'] = operation
        if operation['available']:
            data = read(pointer, 0x148)
            payload = struct.unpack_from('<I', data, 0x144)[0]
            operation.update(raw=data.hex(), byte_0d=data[0xD],
                             payload={'pointer': hex(payload), 'available': available(payload, 0x2CCF)})
            if operation['payload']['available']:
                operation['payload']['byte_2cce'] = read(payload+0x2CCE, 1)[0]
    return result


def run(output, card, group23):
    if output.exists():
        raise FileExistsError('Existing evidence is immutable')
    master = Path(__file__).resolve().parents[1] / 'artifacts/z62-reference-1.70/master.bin'
    original = master.read_bytes()
    master_sha = hashlib.sha256(original).hexdigest()
    if master_sha != 'bb83613121f843d65101da936d942acdc513d86dbd3abc26259d0d870d03f5d4':
        raise ValueError('Requires the unchanged original C1.70 master member')
    for address, expected in ANCHORS.items():
        offset = address-0x10020000
        if original[offset:offset+len(expected)//2].hex() != expected:
            raise ValueError('Completion gate instruction does not match the original member')
    fixture = parent.parent.parent.probe.baseline
    original_route = fixture.route.run

    def instrumented(*args, **kwargs):
        original_hit = kwargs.get('extra_hit_hook')

        def hit(remote, registers):
            result = original_hit(remote, registers) if original_hit else {}
            if registers['pc'] in POINTS:
                extended = dict(registers)
                if registers['pc'] == 0x1032448C:
                    extended['r8'] = remote.get(remote.regs(), 'r8')
                result['completion_gate'] = capture(remote, extended)
            return result

        kwargs['only_points'] = {**kwargs.get('only_points', {}), **POINTS}
        kwargs['extra_hit_hook'] = hit
        kwargs['max_stops'] = 2000
        return original_route(*args, **kwargs)

    with patch.object(fixture.route, 'run', instrumented):
        receipt = parent.run(output, card, group23, enabled=True)
    trace = json.loads((output / 'trace.json').read_text(encoding='utf-8'))
    rows = [{'sequence': row['sequence'], 'guest_seconds': row['state']['virtual_seconds'],
             'thread': row['thread'], 'registers': row['registers'],
             **row['extra_observation']['completion_gate']}
            for row in trace.get('hits', []) if 'completion_gate' in row.get('extra_observation', {})]
    result = {'schema': 1, 'profile': VERSION, 'completed_observation': receipt['completed'],
              'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'master_member_with_crc_sha256': master_sha, 'points': {hex(k): v for k, v in POINTS.items()},
              'snapshots': rows, 'stop_reason': trace.get('stop_reason'),
              'process_closed': trace.get('process_closed'),
              'snapshots_atomic': False, 'guest_software_written_by_host': False,
              'guest_functions_called_by_host': False, 'hardware_completion_verified': False,
              'mode_recovery_verified': False, 'whole_camera_verified': False,
              'physical_photo_video_identity_verified': False, 'camera_accessed': False}
    with (output / 'completion.json').open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2)
    print(json.dumps({'completed_observation': result['completed_observation'],
                      'completion_gate_snapshots': len(rows), 'stop_reason': result['stop_reason']}), flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--card', type=Path, required=True)
    parser.add_argument('--group23', type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(0 if run(args.output, args.card, args.group23)['completed_observation'] else 1)
