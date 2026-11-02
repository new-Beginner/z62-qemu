"""Observe original work cancellation, descriptor signals and wait returns.

No signal or guest field is supplied by this observer. Native cancellation can
satisfy a wait, so successful returns do not assert hardware image completion.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
from unittest.mock import patch

import trace_z62_work_event_waits as waits

VERSION = '2026.11.02-work-signal-route-r42'
WORK_CALL, WORK_RETURN = 0x102675E4, 0x102675E8
CANCEL_CALL, CANCEL_RETURN, CANCEL_STORE = 0x1026BA20, 0x1026BA24, 0x102B5B30
SIGNAL_ENTRY, SIGNAL_SET = 0x102E900E, 0x102E9018
ANCHORS = {WORK_CALL: '4ef0cbfa', WORK_RETURN: '08b10020',
           CANCEL_CALL: '4af074f8', CANCEL_RETURN: 'f6e70020', CANCEL_STORE: '606000e0',
           SIGNAL_ENTRY: '0268002a', SIGNAL_SET: '74f0acb9'}
POINTS = {WORK_CALL: 'work-result-wait-call', WORK_RETURN: 'work-result-wait-return',
          CANCEL_CALL: 'work-cancel-signal-call', CANCEL_RETURN: 'work-cancel-signal-return',
          CANCEL_STORE: 'work-cancel-counter-store', SIGNAL_ENTRY: 'descriptor-signal-entry',
          SIGNAL_SET: 'descriptor-signal-os-dispatch'}


def decode_work(pointer, raw):
    if type(pointer) is not int or not isinstance(raw, bytes) or len(raw) != 128:
        raise ValueError('Require one complete live work snapshot')
    word = lambda offset: struct.unpack_from('<I', raw, offset)[0]
    count = word(0x1C)
    known = 1 <= count <= 5 and word(0x60) == count
    descriptors = []
    for index in range(count if known else 0):
        data = raw[0x24+12*index:0x30+12*index]
        event, mask, group = struct.unpack('<III', data)
        descriptors.append({'event_object': hex(event), 'mask': mask, 'group': group & 0xFF,
                            'raw_0c': data.hex()})
    return {'pointer': hex(pointer), 'raw_80': raw.hex(), 'layout_known': known,
            'identity_word0': word(0), 'pending_word4': word(4),
            'component_pointer': hex(word(8)), 'operation_pointer': hex(word(12)),
            'descriptor_count': count, 'counter_word20': word(0x20), 'descriptors': descriptors,
            'identity': [hex(pointer), word(0), word(8), word(12),
                         [d['raw_0c'] for d in descriptors]]}


def capture(memory, registers):
    pc = registers.get('pc')
    if type(pc) is not int or pc not in ANCHORS:
        raise ValueError('Not an original work/signal route point')

    def read(address, size):
        data = memory.read(address, size)
        if not isinstance(data, bytes) or len(data) != size:
            raise ValueError('Incomplete live work/signal observation')
        return data

    def ram(pointer, size):
        return type(pointer) is int and 0xC0000000 <= pointer <= 0xE0000000-size

    code = read(pc, 4).hex()
    result = {'read_only': True, 'snapshots_atomic': False, 'source_instruction_4': code,
              'source_instruction_matches': code == ANCHORS[pc]}
    if not result['source_instruction_matches']:
        return result
    if pc in (WORK_RETURN, CANCEL_RETURN):
        result['return_r0'] = registers['r0']
        if pc == CANCEL_RETURN:
            result['work_pointer'] = hex(registers['r4'])
        return result
    if pc == CANCEL_STORE:
        result.update(counter_address=hex(registers['r4']+4), counter_value=registers['r0'],
                      ram_after_store_read=False)
        return result
    if pc == SIGNAL_SET:
        result.update(event_object=hex(registers['r0']), mask=registers['r1'])
        return result
    if pc == SIGNAL_ENTRY:
        pointer = registers['r0']
        result.update(descriptor_pointer=hex(pointer), descriptor_known=ram(pointer, 12))
        if result['descriptor_known']:
            raw = read(pointer, 12)
            event, mask, group = struct.unpack('<III', raw)
            result['descriptor'] = {'event_object': hex(event), 'mask': mask,
                                    'group': group & 0xFF, 'raw_0c': raw.hex()}
        return result
    pointer = registers['r1']-0x1C if pc == WORK_CALL else registers['r4']
    result['work_available'] = ram(pointer, 128)
    if pc == CANCEL_CALL and registers['r1'] != pointer+0x1C:
        result.update(work_available=False, argument_mismatch=True)
    if result['work_available']:
        result['work'] = decode_work(pointer, read(pointer, 128))
    return result


def correlate(trace):
    pending, cancellations, incomplete, signal_entries, signals = {}, [], [], {}, []
    work_pending, work_waits, work_incomplete, unmatched = {}, [], [], []
    previous_sequence, previous_time = 0, -1.0
    for hit in trace['hits']:
        data = hit.get('extra_observation', {}).get('work_signal_route')
        if data is None:
            continue
        seq, now = hit['sequence'], hit['state']['virtual_seconds']
        if (type(seq) is not int or seq <= previous_sequence or type(now) not in (int, float) or
                not math.isfinite(now) or now < previous_time):
            raise ValueError('Signal routes require ordered sequence and finite monotone time')
        previous_sequence, previous_time = seq, now
        pc, sp = int(hit['registers']['pc'], 16), int(hit['registers']['sp'], 16)
        if pc not in ANCHORS:
            raise ValueError('Unrecognized signal route point')
        event = {'sequence': seq, 'guest_seconds': now, 'thread': hit['thread'],
                 'registers': hit['registers'], 'snapshot': data}
        if not data.get('source_instruction_matches'):
            unmatched.append(event)
            continue
        key = hit['thread'], sp
        if pc == CANCEL_CALL:
            work = data.get('work')
            if not work or not work['layout_known']:
                unmatched.append(event)
                continue
            if key in pending:
                incomplete.append({**pending.pop(key), 'reason': 'overlapping cancellation frame'})
            pending[key] = {'call': event, 'work': work, 'signals': [], 'stores': []}
        elif pc == CANCEL_RETURN:
            span = pending.pop(key, None)
            if span is None:
                unmatched.append(event)
                continue
            span['return'] = event
            expected = span['work']['counter_word20']-1
            indices = [s['descriptor_index'] for s in span['signals']]
            span.update(dispatched_descriptor_indices=indices,
                local_route_verified=(span['work']['pending_word4'] != 0 and
                    0 <= expected < len(span['work']['descriptors']) and indices == [expected] and
                    len(span['stores']) == 1 and span['stores'][0]['snapshot']['counter_value'] == expected and
                    data['work_pointer'] == span['work']['pointer'] and data['return_r0'] == 1))
            cancellations.append(span)
        elif pc == CANCEL_STORE:
            # 102B5B0C pushes 16 bytes; caller frame is still active.
            span = pending.get((hit['thread'], sp+16))
            if span and data['counter_address'] == hex(int(span['work']['pointer'], 16)+0x20):
                span['stores'].append(event)
            else:
                unmatched.append(event)
        elif pc == SIGNAL_ENTRY:
            if data.get('descriptor', {}).get('event_object', '0x0') != '0x0':
                signal_entries[key] = event
        elif pc == SIGNAL_SET:
            entry = signal_entries.pop(key, None)
            desc = entry['snapshot']['descriptor'] if entry else None
            if not desc or (desc['event_object'], desc['mask']) != (data['event_object'], data['mask']):
                unmatched.append(event)
                continue
            signal = {'entry': entry, 'dispatch': event, 'cancellation_frame_matched': False}
            # 16-byte 102B5B0C + 24-byte 102E9118 frames; 102E900E is a leaf.
            span = pending.get((hit['thread'], sp+40))
            if span:
                base = int(span['work']['pointer'], 16)+0x24
                address = int(entry['snapshot']['descriptor_pointer'], 16)
                index = (address-base)//12
                if (address >= base and (address-base) % 12 == 0 and
                        0 <= index < len(span['work']['descriptors']) and
                        desc == span['work']['descriptors'][index]):
                    signal.update(cancellation_frame_matched=True, descriptor_index=index)
                    span['signals'].append(signal)
            signals.append(signal)
        elif pc == WORK_CALL:
            work = data.get('work')
            if work and work['layout_known']:
                if key in work_pending:
                    work_incomplete.append({**work_pending.pop(key), 'reason': 'overlapping work wait'})
                work_pending[key] = {'call': event, 'work': work}
            else:
                unmatched.append(event)
        elif pc == WORK_RETURN:
            span = work_pending.pop(key, None)
            if span is None:
                unmatched.append(event)
            elif span['call']['registers']['r4'] != hit['registers']['r4']:
                work_incomplete.append({**span, 'return': event, 'reason': 'preserved R4 changed'})
            else:
                work_waits.append({**span, 'return': event,
                                  'guest_seconds_wait': round(now-span['call']['guest_seconds'], 6)})
    incomplete.extend({**s, 'reason': 'observation ended in a cancellation frame'} for s in pending.values())
    work_incomplete.extend({**s, 'reason': 'observation ended in a work wait'} for s in work_pending.values())
    for work in work_waits:
        matches = [c for c in cancellations if c['local_route_verified'] and
                   c['work']['identity'] == work['work']['identity'] and
                   c['return']['sequence'] <= work['return']['sequence']]
        indices = sorted({i for c in matches for i in c['dispatched_descriptor_indices']})
        work['cancel_route_sequences'] = [c['call']['sequence'] for c in matches]
        work['all_descriptor_cancel_routes_observed'] = (
            work['return']['snapshot']['return_r0'] == 1 and
            indices == list(range(work['work']['descriptor_count'])))
    return {'schema': 1, 'cancellations': cancellations, 'incomplete_cancellations': incomplete,
            'signals': signals, 'incomplete_signals': list(signal_entries.values()),
            'unmatched': unmatched, 'work_waits': work_waits,
            'incomplete_work_waits': work_incomplete, 'exclusive_producer_verified': False,
            'allocation_epoch_verified': False,
            'hardware_completion_verified': False, 'mode_recovery_verified': False,
            'whole_camera_verified': False}


def run(output, card, group23):
    if output.exists():
        raise FileExistsError('Existing evidence is immutable')
    profiles, selector = waits.profiles, waits.selector
    build = profiles.hardware.verify_build()
    raw = (Path(__file__).resolve().parents[1]/'artifacts/z62-reference-1.70/master.bin').read_bytes()
    if hashlib.sha256(raw).hexdigest() != 'bb83613121f843d65101da936d942acdc513d86dbd3abc26259d0d870d03f5d4':
        raise ValueError('Requires unchanged C1.70 master member')
    for pc, code in {**ANCHORS, **waits.ANCHORS}.items():
        if raw[pc-0x10020000:pc-0x10020000+4].hex() != code:
            raise ValueError('Signal route instruction differs from original')
    baseline = selector.probe.baseline
    configure_original = baseline.host.configure_command

    def configure(command, *args, **kwargs):
        command = configure_original(command, *args, **kwargs)
        return profiles.statistics.configure_command(profiles.boundary.configure_command(command, True), True)

    def hit(remote, registers):
        if registers['pc'] in ANCHORS:
            return {'work_signal_route': capture(remote, registers)}
        if registers['pc'] in waits.POINTS:
            return {'work_event_wait': waits.capture(remote, registers)}
        return {}

    with patch.object(baseline.host, 'DEFAULT_QEMU', profiles.hardware.DEFAULT_QEMU), \
         patch.object(baseline.host, 'configure_command', configure), \
         patch.object(baseline.route.capture.trace, 'observe_capture', lambda machine: {}), \
         patch.object(baseline.route, 'preview_status', lambda machine: {}):
        trace, fixture = baseline.run(output, card, group23, True, False, 18,
            extra_points={**POINTS, **waits.POINTS}, extra_hit_hook=hit, max_stops=3000,
            automatic_shutter=False, wall_limit=1200, observation_timeout_recovery=True)
    result = {'schema': 1, 'profile': VERSION, 'completed_observation': fixture['observation_completed'],
              'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'qemu_sha256': build['binary_sha256'], 'analysis': correlate(trace),
              'descriptor_waits': waits.pair_waits(trace), 'target_guest_seconds': 18,
              'guest_software_written_by_host': False, 'guest_functions_called_by_host': False,
              'software_event_injected': False, 'mode_recovery_verified': False,
              'hardware_completion_verified': False, 'whole_camera_verified': False, 'camera_accessed': False}
    with (output/'signal-route.json').open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2)
    print(json.dumps({'completed_observation': result['completed_observation'],
        'cancel_frames': len(result['analysis']['cancellations']),
        'verified_cancel_routes': sum(c['local_route_verified'] for c in result['analysis']['cancellations']),
        'signals': len(result['analysis']['signals']),
        'work_waits': len(result['analysis']['work_waits'])}), flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--card', type=Path, required=True)
    parser.add_argument('--group23', type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(0 if run(args.output, args.card, args.group23)['completed_observation'] else 1)
