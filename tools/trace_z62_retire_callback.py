"""Measure one original retirement callback frame and its live request.

Entry/poll spans are model guest time. The return PC reads no request memory:
the original function has already freed its packet and possibly its work object.
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

VERSION = '2026.11.02-retirement-callback-window-r38b'
ENTRY, POLL, BEFORE, AFTER, RETURN = 0x103D32EE, 0x103D3334, 0x103D3356, 0x103D335A, 0x10295578
ENTRY_ARGUMENT = 0x43080001
CALLER_OBJECT = 0xC18649B4
POINTS = {ENTRY: 'retire-callback-entry', POLL: 'retire-after-flag-poll',
          BEFORE: 'retire-before-list-unlink', AFTER: 'retire-after-list-unlink',
          RETURN: 'retire-callback-return'}
ANCHORS = {ENTRY: '2de9f041', POLL: 'e94889f7', BEFORE: '78f766fe',
           AFTER: 'e06e20f0', RETURN: 'f4e770b5'}
WINDOW = {'entry': ENTRY, 'return_pc': RETURN, 'register': 'r0', 'equals': ENTRY_ARGUMENT,
          'points': [POLL, BEFORE, AFTER], 'return_sp_delta': 0, 'gate_return': True}


def capture(remote, registers):
    pc = registers.get('pc')
    if type(pc) is not int or pc not in POINTS:
        raise ValueError('Not an original retirement callback point')
    result = {'stage': POINTS[pc], 'read_only': True, 'snapshots_atomic': False}
    if pc == RETURN:
        return result
    if pc == ENTRY and registers.get('r0') != ENTRY_ARGUMENT:
        result['outside_entry_argument'] = True
        return result

    def read(address, size):
        data = remote.read(address, size)
        if not isinstance(data, bytes) or len(data) != size:
            raise ValueError('Incomplete live retirement callback snapshot')
        return data

    def ram(pointer, size):
        return type(pointer) is int and 0xC0000000 <= pointer <= 0xE0000000-size

    control = read(0xC1864CD0, 8)
    result['context'] = {'raw_08': control.hex(), 'state': control[1], 'mode': control[2],
                         'pending_stop': control[4], 'prior_mode': control[5]}
    result['pending_count'] = struct.unpack('<I', read(0xC237A8BC, 4))[0]
    if pc == ENTRY and registers.get('r4') == CALLER_OBJECT:
        caller = read(CALLER_OBJECT+0x20, 8)
        result['caller_fifo_handle'] = hex(struct.unpack_from('<I', caller)[0])
        result['caller_dispatcher_pointer'] = hex(struct.unpack_from('<I', caller, 4)[0])
    packet = registers.get('r1') if pc == ENTRY else registers.get('r7')
    result['packet_pointer'] = hex(packet) if type(packet) is int else None
    packet_available = ram(packet, 16)
    if pc == ENTRY:
        packet_data = read(packet, 16) if packet_available else None
        if packet_data is not None:
            result['packet_raw_10'] = packet_data.hex()
        work = struct.unpack_from('<I', packet_data)[0] if packet_data is not None else None
    else:
        work = registers.get('r4')
    result['work_pointer'] = hex(work) if type(work) is int else None
    available = ram(work, 0x3E31)
    result['work'] = {'available': available}
    result['identity_known'] = bool(packet_available and available)
    if available:
        data = read(work, 0x80)
        result['work'].update(raw_80=data.hex(), flags_6c=struct.unpack_from('<I', data, 0x6C)[0],
                              byte_74=data[0x74], operation_pointer=hex(struct.unpack_from('<I', data, 0xC)[0]),
                              busy_3e30=read(work+0x3E30, 1)[0])
    return result


def pair_callbacks(trace):
    pending, calls, incomplete, outside, entries = {}, [], [], [], []
    previous_sequence = 0
    previous_time = -1.0
    for hit in trace['hits']:
        data = hit.get('extra_observation', {}).get('retire_callback')
        if data is None:
            continue
        sequence = hit['sequence']
        now = hit['state']['virtual_seconds']
        if (type(sequence) is not int or sequence <= previous_sequence or
                type(now) not in (int, float) or not math.isfinite(now) or now < previous_time):
            raise ValueError('Callback observations require ordered sequences and finite monotone time')
        previous_sequence, previous_time = sequence, now
        pc, stack = int(hit['registers']['pc'], 16), int(hit['registers']['sp'], 16)
        if pc not in POINTS or not isinstance(data, dict):
            raise ValueError('Unrecognized callback observation')
        event = {'sequence': sequence, 'guest_seconds': now, 'thread': hit['thread'],
                 'registers': hit['registers'], 'snapshot': data}
        key = hit['thread'], stack if pc in (ENTRY, RETURN) else stack+24
        if pc == ENTRY:
            if int(hit['registers']['r0'], 16) != ENTRY_ARGUMENT:
                outside.append(event)
                continue
            if key in pending:
                incomplete.append({**pending.pop(key), 'reason': 'overlapping entry in the same frame'})
            entries.append(event)
            pending[key] = {'thread': hit['thread'], 'caller_sp': hex(stack),
                            'packet_pointer': data.get('packet_pointer'),
                            'work_pointer': data.get('work_pointer'),
                            'identity_known': data.get('identity_known', False), 'entry': event, 'points': {}}
            continue
        span = pending.get(key)
        if span is None:
            outside.append(event)
            continue
        if pc == RETURN:
            span = pending.pop(key)
            if (not span['identity_known'] or 'poll' not in span['points'] or
                    ('before' in span['points']) != ('after' in span['points'])):
                incomplete.append({**span, 'return': event,
                                   'reason': 'missing live identity, poll exit or paired unlink points'})
                continue
            start, polled = span['entry']['guest_seconds'], span['points']['poll']['guest_seconds']
            calls.append({**span, 'return': event, 'entry_to_poll_seconds': round(polled-start, 6),
                          'callback_seconds': round(now-start, 6),
                          'after_poll_seconds': round(now-polled, 6),
                          'unlink_before_observed': 'before' in span['points'],
                          'unlink_after_observed': 'after' in span['points']})
            continue
        if (not data.get('identity_known') or data.get('packet_pointer') != span['packet_pointer'] or
                data.get('work_pointer') != span['work_pointer']):
            incomplete.append({**pending.pop(key), 'mismatched_event': event,
                               'reason': 'live request identity changed or unavailable'})
            continue
        name = {POLL: 'poll', BEFORE: 'before', AFTER: 'after'}[pc]
        if ((name != 'poll' and 'poll' not in span['points']) or
                (name == 'after' and 'before' not in span['points'])):
            incomplete.append({**pending.pop(key), 'out_of_order_event': event,
                               'reason': 'callback body points out of native order'})
        elif name in span['points']:
            incomplete.append({**pending.pop(key), 'duplicate_event': event,
                               'reason': 'duplicate callback body point'})
        else:
            span['points'][name] = event
    incomplete.extend({**span, 'reason': 'observation ended in an open callback'} for span in pending.values())
    return {'schema': 1, 'calls': calls, 'incomplete': incomplete, 'outside_scope': outside,
            'entries': entries, 'all_observed_frames_completed': bool(calls) and not incomplete,
            'correlation': 'native sequence, same CPU, exact entry/return SP and body SP-24, live packet/work identity',
            'input_stop_reason': trace.get('stop_reason'),
            'input_window_active_at_end': trace.get('breakpoint_window_active'),
            'input_process_closed': trace.get('process_closed'),
            'hardware_completion_verified': False, 'mode_recovery_verified': False, 'whole_camera_verified': False}


def run(output, card, group23):
    if output.exists():
        raise FileExistsError('Existing evidence is immutable')
    build = profiles.hardware.verify_build()
    root = Path(__file__).resolve().parents[1]
    raw = (root/'artifacts/z62-reference-1.70/master.bin').read_bytes()
    if hashlib.sha256(raw).hexdigest() != 'bb83613121f843d65101da936d942acdc513d86dbd3abc26259d0d870d03f5d4':
        raise ValueError('Requires the unchanged original C1.70 master member')
    for address, expected in ANCHORS.items():
        if raw[address-0x10020000:address-0x10020000+4].hex() != expected:
            raise ValueError('Callback window instruction differs from the original member')
    fixture = selector.probe.baseline
    original_configure, original_route = fixture.host.configure_command, fixture.route.run

    def configure(command, *args, **kwargs):
        result = original_configure(command, *args, **kwargs)
        return profiles.statistics.configure_command(profiles.boundary.configure_command(result, True), True)

    def instrumented(*args, **kwargs):
        original_hit = kwargs.get('extra_hit_hook')

        def hit(remote, registers):
            result = original_hit(remote, registers) if original_hit else {}
            if registers['pc'] in POINTS:
                result['retire_callback'] = capture(remote, registers)
            return result

        kwargs.update(only_points={**kwargs.get('only_points', {}), **POINTS},
                      breakpoint_window=WINDOW, max_stops=2500, extra_hit_hook=hit)
        return original_route(*args, **kwargs)

    with patch.object(fixture.host, 'configure_command', configure), \
         patch.object(fixture.route, 'run', instrumented):
        receipt = selector.run(output, card, group23)
    trace_path = output/'trace.json'
    trace = json.loads(trace_path.read_text(encoding='utf-8'))
    analysis = pair_callbacks(trace)
    result = {'schema': 1, 'profile': VERSION, 'completed_observation': receipt['completed'],
              'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'trace_sha256': hashlib.sha256(trace_path.read_bytes()).hexdigest(),
              'qemu_sha256': build['binary_sha256'], 'call_frame_window_enabled': True,
              'entry_r0_argument': hex(ENTRY_ARGUMENT),
              'window': WINDOW, 'window_active_at_end': trace.get('breakpoint_window_active'),
              'analysis': analysis, 'raw_boundary_requested': True, 'continuous_statistics_requested': True,
              'guest_software_written_by_host': False, 'guest_functions_called_by_host': False,
              'mode_recovery_verified': False, 'whole_camera_verified': False, 'camera_accessed': False}
    with (output/'callback.json').open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2)
    print(json.dumps({'completed_observation': result['completed_observation'],
                      'paired_callbacks': len(analysis['calls']), 'incomplete_frames': len(analysis['incomplete']),
                      'window_active_at_end': result['window_active_at_end']}), flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--card', type=Path, required=True)
    parser.add_argument('--group23', type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(0 if run(args.output, args.card, args.group23)['completed_observation'] else 1)
