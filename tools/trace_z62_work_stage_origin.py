"""Read the actual stage behind 102675F2 and native changes to one observed work.

Fixed watched addresses are a bounded hypothesis from r42. The trace must show
what occupies them; their address alone is not a global allocation identity.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
from unittest.mock import patch

import trace_z62_work_signal_route as signals
from trace_z62_retire_count import stack_context

VERSION = '2026.11.02-work-stage-origin-r43b'
NORMAL_ENTRY, WORK_CALL = 0x102675F2, signals.WORK_CALL
WORK_ADDRESS = 0xC2D1A9C0
WATCHES = {WORK_ADDRESS: 4, WORK_ADDRESS+12: 4}
ANCHORS = {NORMAL_ENTRY: '00f11c01', WORK_CALL: '4ef0cbfa'}
POINTS = {NORMAL_ENTRY: 'work-counted-stage-entry', WORK_CALL: 'work-wait-identity'}


def capture(memory, registers):
    pc = registers.get('pc')
    if type(pc) is not int or pc not in ANCHORS:
        raise ValueError('Not an original work stage observation')

    def read(address, size):
        data = memory.read(address, size)
        if not isinstance(data, bytes) or len(data) != size:
            raise ValueError('Incomplete live stage origin snapshot')
        return data

    def ram(address, size):
        return type(address) is int and 0xC0000000 <= address <= 0xE0000000-size

    code = read(pc, 4).hex()
    result = {'read_only': True, 'snapshots_atomic': False,
              'source_instruction_4': code, 'source_instruction_matches': code == ANCHORS[pc],
              'dispatcher_verified': False}
    if not result['source_instruction_matches']:
        return result
    pointer = registers['r0'] if pc == NORMAL_ENTRY else registers['r1']-0x1C
    result['work_available'] = ram(pointer, 128)
    if result['work_available']:
        result['work'] = signals.decode_work(pointer, read(pointer, 128))
    if pc != NORMAL_ENTRY or not result['work_available'] or registers.get('lr') != 0x1029A77F:
        return result
    stage = registers.get('r4')
    result.update(stage_object=hex(stage) if type(stage) is int else None,
                  worker_pointer=hex(registers['r7']))
    if not ram(stage, 48):
        return result
    raw = read(stage, 48)
    work, table = struct.unpack_from('<II', raw)
    index = struct.unpack_from('<I', raw, 0x24)[0]
    result.update(stage_raw_30=raw.hex(), stage_index=index, table_pointer=hex(table),
                  stage_work_matches=work == pointer,
                  stage_component_matches=registers['r6'] == int(result['work']['component_pointer'], 16))
    if work != pointer or not result['stage_component_matches'] or not 0 <= index < 20 or not ram(table, 240):
        return result
    data = read(table, 240)
    stages = []
    for i in range(20):
        row = data[12*i:12*i+12]
        _, setup, poll = struct.unpack('<III', row)
        stages.append({'index': i, 'flag': row[0], 'setup_pointer': hex(setup),
                       'poll_pointer': hex(poll), 'raw_0c': row.hex()})
    result.update(table_raw_f0=data.hex(), table_sha256=hashlib.sha256(data).hexdigest(), stages=stages,
                  dispatcher_verified=stages[index]['poll_pointer'] == hex(NORMAL_ENTRY | 1))
    return result


def extract_writes(trace):
    result = []
    for hit in trace['hits']:
        address = hit.get('watch_address')
        if address not in {hex(x) for x in WATCHES}:
            continue
        values = []
        for field in ('watch_before', 'watch_after'):
            raw = hit.get(field)
            if not isinstance(raw, str):
                raise ValueError('Missing native work field evidence')
            data = bytes.fromhex(raw)
            if len(data) != 4:
                raise ValueError('Incomplete native work field word')
            values.append(struct.unpack('<I', data)[0])
        result.append({'sequence': hit['sequence'], 'guest_seconds': hit['state']['virtual_seconds'],
                       'thread': hit['thread'], 'pc': hit['registers']['pc'],
                       'registers': hit['registers'], 'address': address,
                       'field': 'word0' if address == hex(WORK_ADDRESS) else 'operation_pointer',
                       'before': values[0], 'after': values[1],
                       'instruction_4': hit['watch_instruction_4'],
                       'stack_context': hit.get('extra_observation', {}).get('work_origin_stack')})
    return result


def run(output, card, group23):
    if output.exists():
        raise FileExistsError('Existing evidence is immutable')
    profiles, selector = signals.waits.profiles, signals.waits.selector
    build = profiles.hardware.verify_build()
    original = (Path(__file__).resolve().parents[1]/'artifacts/z62-reference-1.70/master.bin').read_bytes()
    if hashlib.sha256(original).hexdigest() != 'bb83613121f843d65101da936d942acdc513d86dbd3abc26259d0d870d03f5d4':
        raise ValueError('Requires unchanged original C1.70 master')
    for pc, expected in ANCHORS.items():
        if original[pc-0x10020000:pc-0x10020000+4].hex() != expected:
            raise ValueError('Stage origin instruction differs from original')
    baseline = selector.probe.baseline
    configure_original, route_original = baseline.host.configure_command, baseline.route.run

    def configure(command, *args, **kwargs):
        command = configure_original(command, *args, **kwargs)
        return profiles.statistics.configure_command(profiles.boundary.configure_command(command, True), True)

    def hit(remote, registers):
        result = {'work_origin_stack': stack_context(remote, registers)}
        if registers['pc'] in POINTS:
            result['work_stage_origin'] = capture(remote, registers)
        return result

    def route(*args, **kwargs):
        kwargs.update(write_watchpoints=WATCHES, breakpoint_window=None)
        return route_original(*args, **kwargs)

    with patch.object(baseline.host, 'DEFAULT_QEMU', profiles.hardware.DEFAULT_QEMU), \
         patch.object(baseline.host, 'configure_command', configure), \
         patch.object(baseline.route, 'run', route), \
         patch.object(baseline.route.capture.trace, 'observe_capture', lambda machine: {}), \
         patch.object(baseline.route, 'preview_status', lambda machine: {}):
        trace, fixture = baseline.run(output, card, group23, True, False, 18,
            extra_points=POINTS, extra_hit_hook=hit, max_stops=2500,
            automatic_shutter=False, wall_limit=1200, observation_timeout_recovery=True)
    observations = [{'sequence': h['sequence'], 'guest_seconds': h['state']['virtual_seconds'],
                     'thread': h['thread'], 'registers': h['registers'],
                     'snapshot': h['extra_observation']['work_stage_origin']}
                    for h in trace['hits'] if 'work_stage_origin' in h.get('extra_observation', {})]
    result = {'schema': 1, 'profile': VERSION, 'completed_observation': fixture['observation_completed'],
              'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'qemu_sha256': build['binary_sha256'], 'observations': observations,
              'native_writes': extract_writes(trace), 'watched_work_hypothesis': hex(WORK_ADDRESS),
              'target_guest_seconds': 18, 'allocation_epoch_verified': False,
              'guest_software_written_by_host': False, 'guest_functions_called_by_host': False,
              'software_event_injected': False, 'mode_recovery_verified': False,
              'hardware_completion_verified': False, 'whole_camera_verified': False, 'camera_accessed': False}
    with (output/'stage-origin.json').open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2)
    print(json.dumps({'completed_observation': result['completed_observation'],
                      'native_writes': len(result['native_writes']),
                      'stage_tables': sum(o['snapshot']['dispatcher_verified'] for o in observations)}), flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--card', type=Path, required=True)
    parser.add_argument('--group23', type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(0 if run(args.output, args.card, args.group23)['completed_observation'] else 1)
