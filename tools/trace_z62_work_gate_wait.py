"""Read native first-stage event and output-queue call/return contracts.

Result registers and returned event bits remain raw values. A bounded duration
or a zero value is not itself a successful hardware-completion assertion.
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

VERSION = '2026.11.02-work-resource-gate-r40'
CALLS = {0x1026B93E: ('resource-event', 0x1026B942),
         0x102675E4: ('output-queue', 0x102675E8)}
RETURNS = {ret: call for call, (_, ret) in CALLS.items()}
ANCHORS = {0x1026B93E: 'f1f03efd', 0x1026B942: '00980028',
           0x102675E4: '4ef0cbfa', 0x102675E8: '08b10020'}
POINTS = {pc: ('work-' + CALLS[pc][0] + '-call') for pc in CALLS}
POINTS.update({ret: 'work-' + CALLS[call][0] + '-return' for ret, call in RETURNS.items()})


def capture(memory, registers):
    pc = registers.get('pc')
    if type(pc) is not int or pc not in ANCHORS:
        raise ValueError('Not an original work-gate call/return point')

    def read(address, size):
        data = memory.read(address, size)
        if not isinstance(data, bytes) or len(data) != size:
            raise ValueError('Incomplete native work-gate observation')
        return data

    def ram(pointer, size):
        return type(pointer) is int and 0xC0000000 <= pointer <= 0xE0000000-size

    code = read(pc, 4).hex()
    result = {'read_only': True, 'source_instruction_4': code,
              'source_instruction_matches': code == ANCHORS[pc]}
    if not result['source_instruction_matches']:
        return result
    call = pc if pc in CALLS else RETURNS[pc]
    api = CALLS[call][0]
    result.update(api=api, phase='call' if pc in CALLS else 'return', snapshots_atomic=False,
                  resource_flag=struct.unpack('<I', read(0xC18647CC, 4))[0])
    control = read(0xC1864CD0, 8)
    result['control'] = {'state': control[1], 'mode': control[2],
                         'pending_stop': control[4], 'prior_mode': control[5]}
    if pc in CALLS:
        if api == 'resource-event':
            result['arguments'] = {'object': hex(registers['r0']), 'mask': registers['r1'],
                                   'output_pointer': hex(registers['r2']),
                                   'output_equals_sp': registers['r2'] == registers['sp'],
                                   'wait_parameter': registers['r3']}
            work = registers.get('r4')
        else:
            result['arguments'] = {'object': hex(registers['r0']),
                                   'output_pointer': hex(registers['r1']),
                                   'wait_parameter': registers['r2']}
            work = registers['r1']-0x1C
        result['work_pointer'] = hex(work) if type(work) is int else None
        result['work_available'] = ram(work, 128)
        if result['work_available']:
            data = read(work, 128)
            op = struct.unpack_from('<I', data, 0xC)[0]
            result.update(work_raw_80=data.hex(), work_cancel_word=struct.unpack_from('<I', data, 4)[0],
                          work_byte74=data[0x74], operation_pointer=hex(op))
            if ram(op, 0x274):
                result['operation_word270'] = struct.unpack('<I', read(op+0x270, 4))[0]
    else:
        result['return_r0'] = registers['r0']
    if api == 'resource-event':
        stack = registers['sp']
        result['output_bits_known'] = ram(stack, 4)
        if result['output_bits_known']:
            result['output_bits'] = struct.unpack('<I', read(stack, 4))[0]
    return result


def pair_waits(trace):
    pending, waits, incomplete, outside = {}, [], [], []
    previous_sequence, previous_time = 0, -1.0
    for hit in trace['hits']:
        data = hit.get('extra_observation', {}).get('work_gate_wait')
        if data is None:
            continue
        seq, now = hit['sequence'], hit['state']['virtual_seconds']
        if (type(seq) is not int or seq <= previous_sequence or type(now) not in (int, float) or
                not math.isfinite(now) or now < previous_time):
            raise ValueError('Wait records need ordered native sequence and finite monotone time')
        previous_sequence, previous_time = seq, now
        pc = int(hit['registers']['pc'], 16)
        if pc not in ANCHORS:
            raise ValueError('Unexpected work-gate point')
        event = {'sequence': seq, 'guest_seconds': now, 'thread': hit['thread'],
                 'registers': hit['registers'], 'snapshot': data}
        if not data.get('source_instruction_matches'):
            outside.append(event)
            continue
        call = pc if pc in CALLS else RETURNS[pc]
        key = hit['thread'], int(hit['registers']['sp'], 16), call
        if pc in CALLS:
            if key in pending:
                incomplete.append({**pending.pop(key), 'reason': 'new call before the observed return'})
            pending[key] = {'call_pc': hex(call), 'api': CALLS[call][0], 'call': event}
            continue
        span = pending.pop(key, None)
        if span is None:
            outside.append(event)
        elif int(span['call']['registers']['r4'], 16) != int(hit['registers']['r4'], 16):
            incomplete.append({**span, 'return': event, 'reason': 'preserved frame R4 changed'})
        else:
            waits.append({**span, 'return': event,
                          'guest_seconds_wait': round(now-span['call']['guest_seconds'], 6)})
    incomplete.extend({**span, 'reason': 'observation ended before the native return'} for span in pending.values())
    return {'schema': 1, 'waits': waits, 'incomplete': incomplete, 'outside_scope': outside,
            'correlation': 'same callsite, native CPU, exact caller SP and preserved R4',
            'hardware_completion_verified': False, 'mode_recovery_verified': False,
            'whole_camera_verified': False}


def run(output, card, group23):
    if output.exists():
        raise FileExistsError('Existing evidence is immutable')
    build = profiles.hardware.verify_build()
    root = Path(__file__).resolve().parents[1]
    raw = (root/'artifacts/z62-reference-1.70/master.bin').read_bytes()
    if hashlib.sha256(raw).hexdigest() != 'bb83613121f843d65101da936d942acdc513d86dbd3abc26259d0d870d03f5d4':
        raise ValueError('Requires the unchanged original C1.70 master member')
    for address, code in ANCHORS.items():
        if raw[address-0x10020000:address-0x10020000+4].hex() != code:
            raise ValueError('Work-gate opcode differs from original')
    baseline = selector.probe.baseline
    original_configure = baseline.host.configure_command

    def configure(command, *args, **kwargs):
        result = original_configure(command, *args, **kwargs)
        return profiles.statistics.configure_command(profiles.boundary.configure_command(result, True), True)

    def hit(remote, registers):
        return {'work_gate_wait': capture(remote, registers)} if registers['pc'] in ANCHORS else {}

    with patch.object(baseline.host, 'DEFAULT_QEMU', profiles.hardware.DEFAULT_QEMU), \
         patch.object(baseline.host, 'configure_command', configure), \
         patch.object(baseline.route.capture.trace, 'observe_capture', lambda machine: {}), \
         patch.object(baseline.route, 'preview_status', lambda machine: {}):
        trace, fixture = baseline.run(output, card, group23, True, False, 18,
            extra_points=POINTS, extra_hit_hook=hit, max_stops=1200,
            automatic_shutter=False, wall_limit=900, observation_timeout_recovery=True)
    result = {'schema': 1, 'profile': VERSION, 'completed_observation': fixture['observation_completed'],
              'qemu_sha256': build['binary_sha256'], 'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'analysis': pair_waits(trace), 'target_guest_seconds': 18,
              'scope': 'Native initialization call/return timing; no sustained selector transition.',
              'guest_software_written_by_host': False, 'guest_functions_called_by_host': False,
              'software_event_injected': False, 'mode_recovery_verified': False,
              'whole_camera_verified': False, 'camera_accessed': False}
    with (output/'work-gate-waits.json').open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2)
    print(json.dumps({'completed_observation': result['completed_observation'],
                      'paired_waits': len(result['analysis']['waits']),
                      'incomplete_waits': len(result['analysis']['incomplete'])}), flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--card', type=Path, required=True)
    parser.add_argument('--group23', type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(0 if run(args.output, args.card, args.group23)['completed_observation'] else 1)
