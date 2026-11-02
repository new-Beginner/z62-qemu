"""Read the live 20-entry work-stage table at the original dispatcher entry.

This short initialization experiment identifies callbacks. It does not execute
callbacks itself, assert a selected stage ran, or replace the 55-second tests.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
from unittest.mock import patch

import trace_z62_selector_processing as profiles
import trace_z62_selector_route as selector

VERSION = '2026.11.02-work-stage-table-r39'
DISPATCHER, WORKER = 0x1029A7D4, 0xC18649B4


def capture(memory, registers):
    if registers.get('pc') != DISPATCHER:
        raise ValueError('Not the original work dispatcher entry')
    result = {'read_only': True, 'snapshots_atomic': False, 'table_known': False,
              'stage_execution_verified': False}
    if registers.get('r0') != WORKER:
        result['outside_worker'] = True
        return result

    def ram(pointer, size):
        return type(pointer) is int and 0xC0000000 <= pointer <= 0xE0000000-size

    def read(address, size):
        data = memory.read(address, size)
        if not isinstance(data, bytes) or len(data) != size:
            raise ValueError('Incomplete live work-stage snapshot')
        return data

    message = registers.get('r1')
    result['message_pointer'] = hex(message) if type(message) is int else None
    if not ram(message, 28):
        return result
    data = read(message, 28)
    result.update(message_raw_1c=data.hex(), callback_pointer=hex(struct.unpack_from('<I', data, 12)[0]),
                  message_code=struct.unpack_from('<I', data, 16)[0])
    stage, callback_data = struct.unpack_from('<II', data, 20)
    result.update(stage_object=hex(stage), callback_data=hex(callback_data))
    if result['message_code'] != 0x43080001 or not ram(stage, 48):
        return result
    data = read(stage, 48)
    work, table = struct.unpack_from('<II', data)
    result.update(stage_object_raw_30=data.hex(), work_pointer=hex(work), table_pointer=hex(table),
                  stage_index=struct.unpack_from('<i', data, 0x24)[0],
                  completion_code=struct.unpack_from('<I', data, 0x28)[0])
    if not ram(table, 240):
        return result
    raw = read(table, 240)
    result.update(table_known=True, table_raw_f0=raw.hex(), table_sha256=hashlib.sha256(raw).hexdigest(),
                  stages=[{'index': n, 'flag': raw[n*12],
                           'raw_0c': raw[n*12:n*12+12].hex(),
                           'setup_pointer': hex(struct.unpack_from('<I', raw, n*12+4)[0]),
                           'poll_pointer': hex(struct.unpack_from('<I', raw, n*12+8)[0])}
                          for n in range(20)])
    if ram(work, 128):
        data = read(work, 128)
        component = struct.unpack_from('<I', data, 8)[0]
        result.update(work_raw_80=data.hex(), work_cancel_word=struct.unpack_from('<I', data, 4)[0],
                      component_pointer=hex(component))
        if ram(component, 0x214):
            result['component_word210'] = struct.unpack('<I', read(component+0x210, 4))[0]
    control = read(0xC1864CD0, 8)
    result['control'] = {'raw_08': control.hex(), 'state': control[1], 'mode': control[2],
                         'pending_stop': control[4], 'prior_mode': control[5]}
    return result


def run(output, card, group23):
    if output.exists():
        raise FileExistsError('Existing evidence is immutable')
    build = profiles.hardware.verify_build()
    root = Path(__file__).resolve().parents[1]
    raw = (root/'artifacts/z62-reference-1.70/master.bin').read_bytes()
    if (hashlib.sha256(raw).hexdigest() != 'bb83613121f843d65101da936d942acdc513d86dbd3abc26259d0d870d03f5d4' or
            raw[DISPATCHER-0x10020000:DISPATCHER-0x10020000+4].hex() != '70b50c46'):
        raise ValueError('Work dispatcher differs from the original member')
    baseline = selector.probe.baseline
    original_configure = baseline.host.configure_command

    def configure(command, *args, **kwargs):
        result = original_configure(command, *args, **kwargs)
        return profiles.statistics.configure_command(profiles.boundary.configure_command(result, True), True)

    def hit(remote, registers):
        return {'work_stage_table': capture(remote, registers)} if registers['pc'] == DISPATCHER else {}

    with patch.object(baseline.host, 'DEFAULT_QEMU', profiles.hardware.DEFAULT_QEMU), \
         patch.object(baseline.host, 'configure_command', configure), \
         patch.object(baseline.route.capture.trace, 'observe_capture', lambda machine: {}), \
         patch.object(baseline.route, 'preview_status', lambda machine: {}):
        trace, fixture = baseline.run(output, card, group23, True, False, 18,
            extra_points={DISPATCHER: 'work-stage-dispatch-entry'}, extra_hit_hook=hit,
            max_stops=250, automatic_shutter=False, wall_limit=900,
            observation_timeout_recovery=True)
    snapshots = [{'sequence': h['sequence'], 'guest_seconds': h['state']['virtual_seconds'],
                  'thread': h['thread'], 'registers': h['registers'],
                  **h['extra_observation']['work_stage_table']}
                 for h in trace['hits'] if 'work_stage_table' in h.get('extra_observation', {})]
    result = {'schema': 1, 'profile': VERSION, 'completed_observation': fixture['observation_completed'],
              'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'qemu_sha256': build['binary_sha256'], 'target_guest_seconds': 18,
              'scope': 'Initialization table discovery; no sustained selector transition.',
              'snapshots': snapshots, 'table_snapshots': sum(s.get('table_known', False) for s in snapshots),
              'stage_execution_verified': False, 'guest_software_written_by_host': False,
              'guest_functions_called_by_host': False, 'software_event_injected': False,
              'mode_recovery_verified': False, 'whole_camera_verified': False, 'camera_accessed': False}
    with (output/'stage-table.json').open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2)
    print(json.dumps({'completed_observation': result['completed_observation'],
                      'stage_table_snapshots': result['table_snapshots']}), flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--card', type=Path, required=True)
    parser.add_argument('--group23', type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(0 if run(args.output, args.card, args.group23)['completed_observation'] else 1)
