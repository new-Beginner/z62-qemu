"""Observe actual transfer registration, IRQ102 statuses and queued messages.

The transfer block at 20100000 is separate from the processor IRQ banks.
Its frozen model reads are passive; IRQ status samples use native CPU values.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
from unittest.mock import patch

import trace_z62_stage_resource_waits as resources

VERSION = '2026.11.02-transfer-bindings-r45b'
WAIT, IRQ_SAMPLE, CONTROL, DATA, COMMAND = 0x102694AE, 0x103BF570, 0x1038B020, 0x103C056A, 0x103B754C
ENQUEUE, DECODE = 0x102BD5E0, 0x102E47B0
HOOKS = {0x1038B1D8: 0xC1809500, 0x1038B1E0: 0xC1809504, 0x1038B1E8: 0xC1809508}
ANCHORS = {WAIT: 'f3f086ff', IRQ_SAMPLE: '8561c661', CONTROL: '10b5c807',
           DATA: '2de9f047', COMMAND: '2de9f041', ENQUEUE: '27f011f9', DECODE: '08690a46',
           0x1038B1D8: '6f491439', 0x1038B1E0: '6d491439', 0x1038B1E8: '6b491439'}
POINTS = {WAIT: 'binding-before-resource-wait', IRQ_SAMPLE: 'native-transfer-status-sample',
          CONTROL: 'transfer-control-callback', DATA: 'transfer-data-status-dispatch',
          COMMAND: 'transfer-command-dispatch', ENQUEUE: 'constructed-input-notification',
          DECODE: 'service-message-decoder'}
POINTS.update({pc: 'library-hook-registration' for pc in HOOKS})


def capture(memory, registers):
    pc = registers.get('pc')
    if type(pc) is not int or pc not in ANCHORS:
        raise ValueError('Not an original transfer binding point')

    def read(address, size):
        data = memory.read(address, size)
        if not isinstance(data, bytes) or len(data) != size:
            raise ValueError('Incomplete transfer binding snapshot')
        return data

    def word(address):
        return struct.unpack('<I', read(address, 4))[0]

    code = read(pc, 4).hex()
    result = {'read_only': True, 'snapshots_atomic': False,
              'source_instruction_4': code, 'source_instruction_matches': code == ANCHORS[pc]}
    if not result['source_instruction_matches']:
        return result
    if pc in HOOKS:
        result.update(kind='hook-registration-entry', proposed_hook=hex(registers['r0']),
                      hook_destination=hex(HOOKS[pc]), hook_write_after_read_verified=False)
    elif pc == WAIT:
        transfer = struct.unpack('<10I', read(0x20100000, 40))
        callbacks = struct.unpack('<6I', read(0xC1801D60, 24))
        hooks = struct.unpack('<3I', read(0xC1809500, 12))
        mapping = struct.unpack('<48I', read(0xC1801D78, 192))
        unit_callbacks = struct.unpack('<8I', read(0xC1CF0F40, 32))
        processor = read(0xC1801ECC, 16)
        result.update(kind='wait-binding-snapshot',
            transfer_registers={hex(4*i): value for i, value in enumerate(transfer)},
            transfer_command_callback=hex(callbacks[0]), transfer_control_callback=hex(callbacks[5]),
            transfer_callback_raw_18=struct.pack('<6I', *callbacks).hex(),
            message_decoder_hook=hex(hooks[0]), other_library_hooks=[hex(x) for x in hooks[1:]],
            result_callbacks=[hex(x) for x in unit_callbacks],
            result_status_tables={name: [{'status_mask': mapping[group*16+2*i],
                'payload': mapping[group*16+2*i+1]} for i in range(8)]
                for group, name in enumerate(('status1c_low', 'status1c_high', 'status20'))},
            command_dispatch_hook=hex(word(0xC1809554)),
            processor_mode0=processor[0], processor_mode1=processor[1],
            processor_callback0=hex(struct.unpack_from('<I', processor, 8)[0]),
            processor_callback1=hex(struct.unpack_from('<I', processor, 12)[0]),
            processor_callback_raw_10=processor.hex(),
            command_mode0_raw=read(0xC1D52636, 1)[0], command_mode1_raw=read(0xC1D5267E, 1)[0],
            configuration_semantics_verified=False)
    elif pc == IRQ_SAMPLE:
        result.update(kind='native-irq102-status', register_base=hex(registers['r0']),
            native_status18=registers['r5'], native_status1c=registers['r6'],
            native_status20=registers['r4'], extra_io_status_read=False)
    elif pc in (CONTROL, DATA, COMMAND):
        result.update(kind={CONTROL: 'control-callback', DATA: 'data-status-dispatch',
                            COMMAND: 'command-dispatch'}[pc], argument0_raw=registers['r0'],
                      argument1_raw=registers['r1'])
    else:
        pointer = registers['r0'] if pc == ENQUEUE else registers['r1']
        available = type(pointer) is int and 0xC0000000 <= pointer <= 0xE0000000-32
        result.update(kind='message-enqueue' if pc == ENQUEUE else 'message-decode',
                      message_pointer=hex(pointer), message_available=available)
        if pc == ENQUEUE:
            matches = registers['r0'] == registers['r4']+0x10
            result['constructed_argument_matches'] = matches
            available = available and matches
            result['message_available'] = available
        if available:
            raw = read(pointer, 32)
            result.update(message_raw_20=raw.hex(),
                message_callback=hex(struct.unpack_from('<I', raw, 0xC)[0]),
                message_code_raw=struct.unpack_from('<I', raw, 0x10)[0],
                message_aux_pointer=hex(struct.unpack_from('<I', raw, 0x14)[0]),
                message_payload_raw=struct.unpack_from('<I', raw, 0x18)[0])
    return result


def run(output, card, group23):
    if output.exists():
        raise FileExistsError('Existing evidence is immutable')
    root = Path(__file__).resolve().parents[1]
    raw = (root/'artifacts/z62-reference-1.70/master.bin').read_bytes()
    if hashlib.sha256(raw).hexdigest() != 'bb83613121f843d65101da936d942acdc513d86dbd3abc26259d0d870d03f5d4':
        raise ValueError('Requires unchanged original C1.70 master')
    for pc, expected in ANCHORS.items():
        if raw[pc-0x10020000:pc-0x10020000+4].hex() != expected:
            raise ValueError('Transfer observation instruction differs from original')
    baseline = resources.signals.waits.selector.probe.baseline
    route_original = baseline.route.run

    def route(*args, **kwargs):
        old_hit = kwargs.get('extra_hit_hook')

        def hit(remote, registers):
            result = old_hit(remote, registers) if old_hit else {}
            if registers['pc'] in POINTS:
                result['transfer_binding'] = capture(remote, registers)
            return result

        kwargs.update(only_points={**kwargs.get('only_points', {}), **POINTS},
                      extra_hit_hook=hit, max_stops=5000)
        return route_original(*args, **kwargs)

    with patch.object(baseline.route, 'run', route):
        receipt = resources.run(output, card, group23)
    trace = json.loads((output/'trace.json').read_text(encoding='utf-8'))
    observations = [{'sequence': h['sequence'], 'guest_seconds': h['state']['virtual_seconds'],
                     'thread': h['thread'], 'registers': h['registers'],
                     'snapshot': h['extra_observation']['transfer_binding']}
                    for h in trace['hits'] if 'transfer_binding' in h.get('extra_observation', {})]
    result = {'schema': 1, 'profile': VERSION, 'completed_observation': receipt['completed_observation'],
              'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'parent_source_sha256': receipt['source_sha256'], 'qemu_sha256': receipt['qemu_sha256'],
              'observations': observations, 'target_guest_seconds': 18,
              'guest_software_written_by_host': False, 'guest_functions_called_by_host': False,
              'software_event_injected': False, 'irq_to_message_path_verified': False,
              'hardware_completion_verified': False, 'mode_recovery_verified': False,
              'whole_camera_verified': False, 'camera_accessed': False}
    with (output/'transfer-bindings.json').open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2)
    print(json.dumps({'completed_observation': result['completed_observation'],
                      'binding_observations': len(observations)}), flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--card', type=Path, required=True)
    parser.add_argument('--group23', type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(0 if run(args.output, args.card, args.group23)['completed_observation'] else 1)
