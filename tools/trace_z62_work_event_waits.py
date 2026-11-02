"""Observe each original 102E9144 descriptor wait without supplying events.

102E9168 calls 102E901E with a live descriptor; 102E916C is its return.
The result R0 and raw R3 remain distinct: a timeout does not validate R3.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
from unittest.mock import patch

import trace_z62_selector_processing as profiles
import trace_z62_selector_route as selector

VERSION = '2026.11.02-sequential-work-event-waits-r41b'
CALL, RETURN = 0x102E9168, 0x102E916C
ANCHORS = {CALL: 'fff759ff', RETURN: '00288ed0'}
POINTS = {CALL: 'work-descriptor-wait-call', RETURN: 'work-descriptor-wait-return'}
PRESERVED = ('r4', 'r6', 'r7', 'r8')


def capture(memory, registers):
    pc = registers.get('pc')
    if type(pc) is not int or pc not in ANCHORS:
        raise ValueError('Not an original descriptor wait call/return')

    def read(address, size):
        data = memory.read(address, size)
        if not isinstance(data, bytes) or len(data) != size:
            raise ValueError('Incomplete live descriptor wait observation')
        return data

    def ram(address, size):
        return type(address) is int and 0xC0000000 <= address <= 0xE0000000-size

    code = read(pc, 4).hex()
    result = {'read_only': True, 'snapshots_atomic': False, 'identity_known': False,
              'source_instruction_4': code, 'source_instruction_matches': code == ANCHORS[pc],
              'phase': 'call' if pc == CALL else 'return'}
    if not result['source_instruction_matches']:
        return result
    # The shared hit dictionary deliberately contains only r0-r7. Read r8
    # explicitly from this stopped CPU, without changing the shared adapter.
    if 'r8' not in registers:
        registers = {**registers, 'r8': memory.read_register('r8')}
        result['r8_source'] = 'gdb-read-register'
    else:
        result['r8_source'] = 'callback-dictionary'
    result['frame_registers'] = {name: hex(registers[name]) for name in PRESERVED}
    index, base, selected, timeout = (registers[name] for name in PRESERVED)
    result.update(index=index, array_base=hex(base), selected_mask=selected, wait_parameter=timeout)
    if pc == RETURN:
        result.update(return_r0=registers['r0'], return_r3_raw=registers['r3'])
    if (type(index) is not int or not 0 <= index < 5 or not ram(base, 0x40) or base % 4 or
            type(selected) is not int or not selected & (1 << index) or
            type(timeout) is not int or not 0 <= timeout <= 0xFFFFFFFF):
        result['outside_descriptor_layout'] = True
        return result
    descriptor = base + index*12
    count = struct.unpack('<I', read(base+0x3C, 4))[0]
    result.update(descriptor_count=count, descriptor_pointer=hex(descriptor))
    if not 1 <= count <= 5 or index >= count:
        result['outside_descriptor_count'] = True
        return result
    if pc == CALL and (registers['r0'] != descriptor or registers['r1'] != timeout):
        result['argument_mismatch'] = True
        return result
    raw = read(descriptor, 12)
    event, mask, word8 = struct.unpack('<III', raw)
    result.update(identity_known=True, descriptor_raw_0c=raw.hex(),
                  descriptor={'event_object': hex(event), 'mask': mask,
                              'group': raw[8], 'word_8': word8})
    return result


def pair_waits(trace):
    pending, waits, incomplete, outside = {}, [], [], []
    last_sequence, last_time = 0, -1.0
    for hit in trace['hits']:
        data = hit.get('extra_observation', {}).get('work_event_wait')
        if data is None:
            continue
        sequence, now = hit['sequence'], hit['state']['virtual_seconds']
        if (type(sequence) is not int or sequence <= last_sequence or
                type(now) not in (int, float) or not math.isfinite(now) or now < last_time):
            raise ValueError('Descriptor waits require ordered sequence and finite monotone time')
        last_sequence, last_time = sequence, now
        pc = int(hit['registers']['pc'], 16)
        if pc not in ANCHORS:
            raise ValueError('Unexpected descriptor wait point')
        event = {'sequence': sequence, 'guest_seconds': now, 'thread': hit['thread'],
                 'registers': hit['registers'], 'snapshot': data}
        if not data.get('source_instruction_matches') or not data.get('identity_known'):
            outside.append(event)
            continue
        key = hit['thread'], int(hit['registers']['sp'], 16)
        if pc == CALL:
            if key in pending:
                incomplete.append({**pending.pop(key), 'reason': 'new call in an open frame'})
            pending[key] = {'call': event}
            continue
        span = pending.pop(key, None)
        if span is None:
            outside.append(event)
            continue
        before = span['call']
        same_frame = before['snapshot']['frame_registers'] == data['frame_registers']
        same_descriptor = all(before['snapshot'][name] == data[name]
                              for name in ('descriptor_pointer', 'descriptor_raw_0c'))
        if not same_frame or not same_descriptor:
            incomplete.append({**span, 'return': event, 'reason': 'frame or live descriptor changed'})
        else:
            waits.append({**span, 'return': event,
                          'guest_seconds_wait': round(now-before['guest_seconds'], 6)})
    incomplete.extend({**span, 'reason': 'observation ended before the native return'}
                      for span in pending.values())
    return {'schema': 1, 'waits': waits, 'incomplete': incomplete, 'outside_scope': outside,
            'correlation': 'same native CPU/SP, preserved index/base/selection/timeout and live descriptor bytes',
            'hardware_completion_verified': False, 'mode_recovery_verified': False,
            'whole_camera_verified': False}


def run(output, card, group23):
    if output.exists():
        raise FileExistsError('Existing evidence is immutable')
    build = profiles.hardware.verify_build()
    root = Path(__file__).resolve().parents[1]
    raw = (root/'artifacts/z62-reference-1.70/master.bin').read_bytes()
    if hashlib.sha256(raw).hexdigest() != 'bb83613121f843d65101da936d942acdc513d86dbd3abc26259d0d870d03f5d4':
        raise ValueError('Requires unchanged original C1.70 master member')
    for pc, expected in ANCHORS.items():
        if raw[pc-0x10020000:pc-0x10020000+4].hex() != expected:
            raise ValueError('Descriptor wait instruction differs from original')
    baseline = selector.probe.baseline
    original_configure = baseline.host.configure_command

    def configure(command, *args, **kwargs):
        command = original_configure(command, *args, **kwargs)
        return profiles.statistics.configure_command(profiles.boundary.configure_command(command, True), True)

    def hit(remote, registers):
        return {'work_event_wait': capture(remote, registers)} if registers['pc'] in POINTS else {}

    with patch.object(baseline.host, 'DEFAULT_QEMU', profiles.hardware.DEFAULT_QEMU), \
         patch.object(baseline.host, 'configure_command', configure), \
         patch.object(baseline.route.capture.trace, 'observe_capture', lambda machine: {}), \
         patch.object(baseline.route, 'preview_status', lambda machine: {}):
        trace, fixture = baseline.run(output, card, group23, True, False, 18,
            extra_points=POINTS, extra_hit_hook=hit, max_stops=1600,
            automatic_shutter=False, wall_limit=900, observation_timeout_recovery=True)
    result = {'schema': 1, 'profile': VERSION, 'completed_observation': fixture['observation_completed'],
              'qemu_sha256': build['binary_sha256'], 'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'analysis': pair_waits(trace), 'target_guest_seconds': 18,
              'scope': 'Native initialization descriptor waits; no sustained selector transition.',
              'guest_software_written_by_host': False, 'guest_functions_called_by_host': False,
              'software_event_injected': False, 'mode_recovery_verified': False,
              'whole_camera_verified': False, 'camera_accessed': False}
    with (output/'event-waits.json').open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2)
    print(json.dumps({'completed_observation': result['completed_observation'],
                      'paired_descriptor_waits': len(result['analysis']['waits']),
                      'incomplete_waits': len(result['analysis']['incomplete']),
                      'outside_scope': len(result['analysis']['outside_scope'])}), flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--card', type=Path, required=True)
    parser.add_argument('--group23', type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(0 if run(args.output, args.card, args.group23)['completed_observation'] else 1)
