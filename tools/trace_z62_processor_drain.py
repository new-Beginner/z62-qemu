"""Read original stop flags, list counts and selected native work notifications.

No software event is injected. Empty lists and a clear stop flag are separate
prerequisites, not an assertion that the hardware or the mode change completed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
from unittest.mock import patch

import trace_z62_selector_processing as profiles
import trace_z62_selector_route as selector

VERSION = '2026.11.02-processor-drain-observation-r36'
LISTS = (0xC237A794, 0xC237A7B4, 0xC237A874, 0xC237A894, 0xC237A8B4)
POINTS = {0x103D2ED4: 'stop-native-request8000',
          0x103D2EE2: 'stop-before-final-condition',
          0x103D2F04: 'stop-before-pending-flag-check',
          0x103D2F0E: 'stop-native-request2000',
          0x103CE43E: 'restore-function-entry',
          0x103CE472: 'restore-state4-entry',
          0x103CE494: 'restore-list-predicate-return',
          0x103CE574: 'restore-before-state1-write',
          0x103CF4BE: 'worker-before-byte00-write'}
ANCHORS = {0x103D2ED4: '89f75afd', 0x103D2EE2: 'fb488af7',
           0x103D2F04: '207920b9', 0x103D2F0E: '89f73dfd',
           0x103CE43E: '2de9fc5f', 0x103CE472: '8146c069',
           0x103CE494: '58bba078', 0x103CE574: '61708ce0',
           0x103CF4BE: '2070b448'}


def snapshot(memory):
    def read(address, size):
        data = memory.read(address, size)
        if not isinstance(data, bytes) or len(data) != size:
            raise ValueError('Incomplete processor stop-prerequisite snapshot')
        return data

    control = read(0xC1864CD0, 0xA0)
    region = read(0xC237A794, 0x140)
    lists = {}
    for address in LISTS:
        data = region[address-0xC237A794:address-0xC237A794+32]
        lists[hex(address)] = {'raw': data.hex(), 'count': struct.unpack_from('<I', data, 8)[0]}
    return {'read_only': True, 'snapshots_atomic': False, 'control_raw_a0': control.hex(),
            'state': control[1], 'mode': control[2], 'pending_stop': control[4],
            'prior_mode': control[5], 'lists': lists,
            'control_words': {hex(offset): struct.unpack_from('<I', control, offset)[0]
                              for offset in (0x40, 0x44, 0x48, 0x90, 0x94, 0x98, 0x9C)},
            'three_stop_lists_empty': all(lists[hex(a)]['count'] == 0 for a in LISTS[2:]),
            'stop_flag_zero': control[4] == 0}


def capture(memory, registers):
    pc = registers.get('pc')
    if type(pc) is not int or pc not in POINTS:
        raise ValueError('Not a selected original processor drain point')
    result = {'stage': POINTS[pc], **snapshot(memory)}
    if pc in (0x103D2ED4, 0x103D2F0E):
        result.update(notify_object=hex(registers['r0']), notify_bits=registers['r1'])
    elif pc == 0x103CE494:
        result['predicate_return'] = registers['r0']
    elif pc == 0x103CE574:
        result['before_state_write_value'] = registers['r1']
    elif pc == 0x103CF4BE:
        result['before_byte00_write_value'] = registers['r0']
    return result


def run(output, card, group23):
    if output.exists():
        raise FileExistsError('Existing evidence is immutable')
    build = profiles.hardware.verify_build()
    root = Path(__file__).resolve().parents[1]
    original = (root / 'artifacts/z62-reference-1.70/master.bin').read_bytes()
    master_sha = hashlib.sha256(original).hexdigest()
    if master_sha != 'bb83613121f843d65101da936d942acdc513d86dbd3abc26259d0d870d03f5d4':
        raise ValueError('Requires the unchanged original C1.70 master member')
    for address, wanted in ANCHORS.items():
        if original[address-0x10020000:address-0x10020000+4].hex() != wanted:
            raise ValueError('Processor drain anchor differs from the original instruction')
    fixture = selector.probe.baseline
    original_configure = fixture.host.configure_command
    original_route = fixture.route.run
    samples = []
    next_read = 0.5
    read_at_54 = read_at_end = False

    def configure(command, *args, **kwargs):
        result = original_configure(command, *args, **kwargs)
        return profiles.statistics.configure_command(profiles.boundary.configure_command(result, True), True)

    def instrumented(*args, **kwargs):
        original_hit = kwargs.get('extra_hit_hook')
        original_observe = kwargs.get('extra_observation_hook')

        def hit(remote, registers):
            result = original_hit(remote, registers) if original_hit else {}
            if registers['pc'] in POINTS:
                result['processor_drain'] = capture(remote, registers)
            return result

        def observe(machine, row):
            nonlocal next_read, read_at_54, read_at_end
            event = original_observe(machine, row) if original_observe else None
            now = row['virtual_seconds']
            if now < next_read and not (now >= 54 and not read_at_54) and not (now >= 55 and not read_at_end):
                return event
            next_read = now+5
            read_at_54 |= now >= 54
            read_at_end |= now >= 55

            class Reader:
                def read(self, address, size):
                    values = machine._words(address, size//4)
                    if len(values) != size//4 or any(type(v) is not int or not 0 <= v <= 0xFFFFFFFF for v in values):
                        raise ValueError('Incomplete QMP RAM word observation')
                    return struct.pack('<'+'I'*len(values), *values)

            sample = {'guest_seconds_before_read': now, 'known': False}
            try:
                with machine.io:
                    sample['snapshot'] = snapshot(Reader())
                sample['known'] = True
            except (OSError, RuntimeError, ValueError) as exc:
                sample['error'] = {'type': type(exc).__name__, 'message': str(exc)}
            samples.append(sample)
            return event

        kwargs.update(only_points={**kwargs.get('only_points', {}), **POINTS},
                      breakpoint_window=None, max_stops=1000,
                      extra_hit_hook=hit, extra_observation_hook=observe)
        return original_route(*args, **kwargs)

    with patch.object(fixture.host, 'configure_command', configure), \
         patch.object(fixture.route, 'run', instrumented):
        receipt = selector.run(output, card, group23)
    trace = json.loads((output / 'trace.json').read_text(encoding='utf-8'))
    hits = [{'sequence': row['sequence'], 'guest_seconds': row['state']['virtual_seconds'],
             'thread': row['thread'], 'registers': row['registers'],
             **row['extra_observation']['processor_drain']}
            for row in trace.get('hits', []) if 'processor_drain' in row.get('extra_observation', {})]
    result = {'schema': 1, 'profile': VERSION, 'completed_observation': receipt['completed'],
              'qemu_sha256': build['binary_sha256'], 'master_member_with_crc_sha256': master_sha,
              'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'call_frame_window_enabled': False, 'samples': samples, 'hits': hits,
              'all_periodic_samples_known': bool(samples) and all(s['known'] for s in samples),
              'stop_reason': trace.get('stop_reason'), 'process_closed': trace.get('process_closed'),
              'raw_boundary_requested': True, 'continuous_statistics_requested': True,
              'guest_software_written_by_host': False, 'guest_functions_called_by_host': False,
              'software_event_injected': False, 'hardware_completion_verified': False,
              'mode_recovery_verified': False, 'whole_camera_verified': False, 'camera_accessed': False}
    with (output / 'drain.json').open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2)
    print(json.dumps({'completed_observation': result['completed_observation'],
                      'native_drain_hits': len(hits), 'known_samples': sum(s['known'] for s in samples),
                      'sample_count': len(samples), 'stop_reason': result['stop_reason']}), flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--card', type=Path, required=True)
    parser.add_argument('--group23', type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(0 if run(args.output, args.card, args.group23)['completed_observation'] else 1)
