"""Pair real upstream resource waits with their later original cleanup entry.

Unchanged output bits on a failed wait are not received events. Candidate
notification callsites record scalar arguments and never supply notifications.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
from unittest.mock import patch

import trace_z62_work_signal_route as signals

VERSION = '2026.11.02-stage-resource-waits-r44b'
CLEANUP = 0x102675F2
SOURCE_ENTRY, SOURCE_SKIP = 0x10263D08, 0x10263D1E
SOURCE_POINTS = {SOURCE_ENTRY, SOURCE_SKIP}
CALLS = {0x1026A3A0: {'name': 'stage-a300', 'return': 0x1026A3A4, 'work_register': 'r4', 'output_offset': 8, 'frame_bytes': 40, 'mask': 0x80800000},
         0x102694AE: {'name': 'stage-69446', 'return': 0x102694B2, 'work_register': 'r4', 'output_offset': 0, 'frame_bytes': 40, 'mask': 0x81000000},
         0x1026B552: {'name': 'stage-b3d2', 'return': 0x1026B556, 'work_register': 'r5', 'output_offset': None, 'frame_bytes': 32, 'mask': 0x200}}
RETURNS = {v['return']: k for k, v in CALLS.items()}
PRODUCERS = {0x10264712, 0x10264780, 0x1026524E, 0x1026491C, 0x10263D34}
ANCHORS = {0x1026A3A0: 'f3f00df8', 0x1026A3A4: '18b942f2',
           0x102694AE: 'f3f086ff', 0x102694B2: '2f484ff0',
           0x1026B552: 'f1f072ff', 0x1026B556: 'f1482146', CLEANUP: '00f11c01',
           0x10264712: 'f8f02ffe', 0x10264780: 'f8f0f8fd',
           0x1026524E: 'f8f091f8', 0x1026491C: 'f8f02afd',
           SOURCE_ENTRY: '70b50d46', SOURCE_SKIP: '002802dd', 0x10263D34: 'f9f01efb'}
POINTS = {pc: ('upstream-' + cfg['name'] + '-call') for pc, cfg in CALLS.items()}
POINTS.update({ret: 'upstream-' + CALLS[call]['name'] + '-return' for ret, call in RETURNS.items()})
POINTS.update({pc: 'candidate-resource-notification' for pc in PRODUCERS})
POINTS[CLEANUP] = 'following-counted-cleanup'
POINTS[SOURCE_ENTRY] = 'output-token-source-entry'
POINTS[SOURCE_SKIP] = 'output-token-skip-counter'


def capture(memory, registers):
    pc = registers.get('pc')
    if type(pc) is not int or pc not in ANCHORS:
        raise ValueError('Not an original stage resource point')

    def read(address, size):
        data = memory.read(address, size)
        if not isinstance(data, bytes) or len(data) != size:
            raise ValueError('Incomplete stage resource snapshot')
        return data

    def ram(address, size):
        return type(address) is int and 0xC0000000 <= address <= 0xE0000000-size

    code = read(pc, 4).hex()
    result = {'read_only': True, 'snapshots_atomic': False, 'source_instruction_4': code,
              'source_instruction_matches': code == ANCHORS[pc]}
    if not result['source_instruction_matches']:
        return result
    if pc == SOURCE_ENTRY:
        result.update(notification_code_raw=registers['r0'], notification_payload_raw=registers['r1'])
        return result
    if pc == SOURCE_SKIP:
        value = registers['r0']
        result.update(skip_counter_raw=value,
                      skip_counter_signed=value if value < 0x80000000 else value-0x100000000,
                      source_control_pointer=hex(registers['r4']), source_payload_raw=registers['r5'])
        return result
    if pc in PRODUCERS:
        result.update(event_object=hex(registers['r0']), signal_mask_raw=registers['r1'],
                      target_event_object=registers['r0'] == 0xC18647D8)
        return result
    if pc == CLEANUP:
        pointer = registers['r0']
        result['dispatcher_return_address_matches'] = registers.get('lr') == 0x1029A77F
    else:
        call = pc if pc in CALLS else RETURNS[pc]
        cfg = CALLS[call]
        pointer = registers[cfg['work_register']]
        result.update(api=cfg['name'], phase='call' if pc in CALLS else 'return')
        if pc in CALLS:
            result['arguments'] = {'event_object': hex(registers['r0']), 'mask_raw': registers['r1'],
                                   'wait_parameter': registers['r3']}
            if cfg['output_offset'] is None:
                result['arguments']['mode_raw'] = registers['r2']
            else:
                output = registers['sp'] + cfg['output_offset']
                result['arguments'].update(output_pointer=hex(registers['r2']),
                    output_equals_verified_stack_slot=registers['r2'] == output)
            result['call_contract_matches'] = (
                registers['r0'] == 0xC18647D8 and registers['r1'] == cfg['mask'] and
                registers['r3'] == 1000 and (registers['r2'] == 0 if cfg['output_offset'] is None
                    else result['arguments']['output_equals_verified_stack_slot']))
            if not result['call_contract_matches']:
                result['output_bits_known'] = False
                return result
        else:
            result['return_r0'] = registers['r0']
        if cfg['output_offset'] is not None:
            output = registers['sp']+cfg['output_offset']
            result['output_bits_known'] = ram(output, 4)
            if result['output_bits_known']:
                result['output_bits_raw'] = struct.unpack('<I', read(output, 4))[0]
    result['work_available'] = ram(pointer, 128)
    if result['work_available']:
        raw = read(pointer, 128)
        result['work'] = signals.decode_work(pointer, raw)
        result.update(work_byte74=raw[0x74], work_word64=struct.unpack_from('<I', raw, 0x64)[0])
        if pc in CALLS:
            operation = struct.unpack_from('<I', raw, 12)[0]
            if ram(operation+0xD, 2):
                result['operation_type_channel_raw'] = read(operation+0xD, 2).hex()
    return result


def correlate(trace):
    pending, waits, incomplete, outside, cleanup, producers = {}, [], [], [], [], []
    source_entries, source_skip_counters = [], []
    last_seq, last_time = 0, -1.0
    for hit in trace['hits']:
        data = hit.get('extra_observation', {}).get('stage_resource_wait')
        if data is None:
            continue
        seq, now = hit['sequence'], hit['state']['virtual_seconds']
        if (type(seq) is not int or seq <= last_seq or type(now) not in (int, float) or
                not math.isfinite(now) or now < last_time):
            raise ValueError('Stage resource observations need ordered sequence and finite monotone time')
        last_seq, last_time = seq, now
        pc = int(hit['registers']['pc'], 16)
        if pc not in ANCHORS:
            raise ValueError('Unrecognized stage resource PC')
        event = {'sequence': seq, 'guest_seconds': now, 'thread': hit['thread'],
                 'registers': hit['registers'], 'snapshot': data}
        if not data.get('source_instruction_matches'):
            outside.append(event)
            continue
        if pc in CALLS and not data.get('call_contract_matches'):
            outside.append(event)
            continue
        if pc in SOURCE_POINTS:
            (source_entries if pc == SOURCE_ENTRY else source_skip_counters).append(event)
            continue
        if pc in PRODUCERS:
            producers.append(event)
            continue
        if pc == CLEANUP:
            cleanup.append(event)
            continue
        call = pc if pc in CALLS else RETURNS[pc]
        key = hit['thread'], int(hit['registers']['sp'], 16), call
        if pc in CALLS:
            if key in pending:
                incomplete.append({**pending.pop(key), 'reason': 'new call in an open frame'})
            pending[key] = {'call_pc': hex(call), 'call': event}
        else:
            span = pending.pop(key, None)
            if span is None:
                outside.append(event)
            elif any(span['call']['registers'][r] != hit['registers'][r] for r in ('r4', 'r5')):
                incomplete.append({**span, 'return': event, 'reason': 'preserved native frame changed'})
            else:
                waits.append({**span, 'return': event, 'guest_seconds_wait': round(now-span['call']['guest_seconds'], 6)})
    incomplete.extend({**s, 'reason': 'observation ended before native return'} for s in pending.values())
    associations, used = [], set()
    for end in cleanup:
        work = end['snapshot'].get('work')
        if not work or not end['snapshot'].get('dispatcher_return_address_matches'):
            continue
        candidates = []
        for w in waits:
            cfg = CALLS[int(w['call_pc'], 16)]
            before = w['call']
            if (w['return']['sequence'] < end['sequence'] and w['return']['sequence'] not in used and
                    before['thread'] == end['thread'] and
                    int(before['registers']['sp'], 16)+cfg['frame_bytes'] == int(end['registers']['sp'], 16) and
                    before['snapshot'].get('work', {}).get('identity') == work['identity'] and
                    w['return']['snapshot'].get('work', {}).get('identity') == work['identity']):
                candidates.append(w)
        if candidates:
            latest = max(candidates, key=lambda w: w['return']['sequence'])
            used.add(latest['return']['sequence'])
            associations.append({'wait': latest, 'cleanup': end,
                'return_to_cleanup_seconds': round(end['guest_seconds']-latest['return']['guest_seconds'], 6)})
    return {'schema': 1, 'waits': waits, 'incomplete': incomplete, 'outside_scope': outside,
            'cleanup_entries': cleanup, 'cleanup_after_wait': associations, 'producer_points': producers,
            'source_callback_entries': source_entries, 'source_skip_counters': source_skip_counters,
            'allocation_epoch_verified': False, 'exclusive_producer_verified': False,
            'hardware_completion_verified': False, 'mode_recovery_verified': False, 'whole_camera_verified': False}


def run(output, card, group23):
    if output.exists():
        raise FileExistsError('Existing evidence is immutable')
    profiles, selector = signals.waits.profiles, signals.waits.selector
    build = profiles.hardware.verify_build()
    raw = (Path(__file__).resolve().parents[1]/'artifacts/z62-reference-1.70/master.bin').read_bytes()
    if hashlib.sha256(raw).hexdigest() != 'bb83613121f843d65101da936d942acdc513d86dbd3abc26259d0d870d03f5d4':
        raise ValueError('Requires unchanged C1.70 master')
    for pc, expected in ANCHORS.items():
        if raw[pc-0x10020000:pc-0x10020000+4].hex() != expected:
            raise ValueError('Stage resource instruction differs from original')
    baseline = selector.probe.baseline
    original_configure = baseline.host.configure_command

    def configure(command, *args, **kwargs):
        command = original_configure(command, *args, **kwargs)
        return profiles.statistics.configure_command(profiles.boundary.configure_command(command, True), True)

    def hit(remote, registers):
        return {'stage_resource_wait': capture(remote, registers)} if registers['pc'] in POINTS else {}

    with patch.object(baseline.host, 'DEFAULT_QEMU', profiles.hardware.DEFAULT_QEMU), \
         patch.object(baseline.host, 'configure_command', configure), \
         patch.object(baseline.route.capture.trace, 'observe_capture', lambda machine: {}), \
         patch.object(baseline.route, 'preview_status', lambda machine: {}):
        trace, fixture = baseline.run(output, card, group23, True, False, 18,
            extra_points=POINTS, extra_hit_hook=hit, max_stops=3000,
            automatic_shutter=False, wall_limit=1200, observation_timeout_recovery=True)
    result = {'schema': 1, 'profile': VERSION, 'completed_observation': fixture['observation_completed'],
              'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'qemu_sha256': build['binary_sha256'], 'analysis': correlate(trace), 'target_guest_seconds': 18,
              'guest_software_written_by_host': False, 'guest_functions_called_by_host': False,
              'software_event_injected': False, 'mode_recovery_verified': False,
              'hardware_completion_verified': False, 'whole_camera_verified': False, 'camera_accessed': False}
    with (output/'resource-waits.json').open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2)
    print(json.dumps({'completed_observation': result['completed_observation'],
                      'paired_waits': len(result['analysis']['waits']),
                      'incomplete_waits': len(result['analysis']['incomplete']),
                      'cleanup_associations': len(result['analysis']['cleanup_after_wait'])}), flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--card', type=Path, required=True)
    parser.add_argument('--group23', type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(0 if run(args.output, args.card, args.group23)['completed_observation'] else 1)
