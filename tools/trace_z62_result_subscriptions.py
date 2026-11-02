"""Observe result subscriptions and graph data without producing guest events."""
import argparse
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import struct
import sys
from unittest.mock import patch

import trace_z62_stage_resource_waits as resources

VERSION = '2026.11.02-result-subscriptions-r46'
WAIT = 0x102694AE
REGISTER, REGISTER_STORED = 0x103B76B0, 0x103B76B4
MASK, MASK_STORED = 0x103B76BC, 0x103B76CC
ROUTER, DISPATCH, HANDOFF = 0x103B742A, 0x1038AD1A, 0x102E6A14
GRAPH, SOURCE = 0x103C03BE, 0x10263D08
ANCHORS = {WAIT: 'f3f086ff', REGISTER: '1549c860', REGISTER_STORED: '704780f8',
           MASK: '124a0029', MASK_STORED: '70470e48', ROUTER: 'f0b587b0',
           DISPATCH: '0122b4e7', HANDOFF: '00290ad0', GRAPH: '70b5974d',
           SOURCE: '70b50d46'}
POINTS = {WAIT: 'result-binding-before-wait', REGISTER: 'result-callback-registration',
          REGISTER_STORED: 'result-callback-native-store', MASK: 'result-forward-selection',
          MASK_STORED: 'result-forward-native-store', ROUTER: 'result-common-router',
          DISPATCH: 'result-dispatch-wrapper', HANDOFF: 'library-result-handoff',
          GRAPH: 'native-backend-node-configuration', SOURCE: 'target-resource-source-callback'}


def capture(memory, registers):
    pc = registers.get('pc')
    if type(pc) is not int or pc not in ANCHORS:
        raise ValueError('Not an original result subscription point')

    def read(address, size):
        data = memory.read(address, size)
        if not isinstance(data, bytes) or len(data) != size:
            raise ValueError('Incomplete result subscription snapshot')
        return data

    def ram(address, size):
        return type(address) is int and 0xC0000000 <= address <= 0xE0000000-size

    def context(pointer):
        result = {'pointer': hex(pointer), 'available': ram(pointer, 32)}
        if result['available']:
            raw = read(pointer, 32)
            table = struct.unpack_from('<I', raw, 0x14)[0]
            result.update(raw_20=raw.hex(), callback_table_pointer=hex(table),
                          callback_table_available=ram(table, 12))
            if result['callback_table_available']:
                data = read(table, 12)
                result.update(callback_table_raw_0c=data.hex(),
                              callbacks=[hex(x) for x in struct.unpack('<3I', data)])
        return result

    code = read(pc, 4).hex()
    result = {'read_only': True, 'snapshots_atomic': False,
              'source_instruction_4': code, 'source_instruction_matches': code == ANCHORS[pc],
              'guest_software_written_by_host': False, 'hardware_completion_verified': False}
    if not result['source_instruction_matches']:
        return result
    if pc == HANDOFF:
        mode = registers['r2']
        ctx = context(registers['r1'])
        result.update(kind='library-result-handoff', handoff_argument0_raw=registers['r0'],
                      handoff_mode_raw=mode, library_context=ctx,
                      callback_execution_verified=False)
        if ctx.get('callback_table_available'):
            index = 1 if mode == 0 else 2
            result.update(predicted_message_code_raw=0x42193081 if mode == 0 else 0x42193082,
                          predicted_callback=ctx['callbacks'][index])
    elif pc == GRAPH:
        pointer = registers['r5']
        result.update(kind='native-graph-snapshot', graph_available=False)
        if not ram(pointer, 8):
            return result
        header = read(pointer, 8)
        table, count = struct.unpack('<2I', header)
        result.update(graph_container=hex(pointer), graph_header_raw_08=header.hex())
        if not (1 <= count <= 64 and ram(table, count*16) and
                table <= registers['r0'] < table+count*16 and (registers['r0']-table)%16 == 0):
            return result
        raw = read(table, count*16)
        nodes = []
        for i in range(count):
            record = raw[i*16:(i+1)*16]
            payload = struct.unpack_from('<I', record, 12)[0]
            row = {'index': i, 'address': hex(table+i*16), 'record_16': record.hex(),
                   'type_byte': record[0], 'physical_unit': record[1],
                   'payload_pointer': hex(payload), 'payload_available': ram(payload, 512)}
            if row['payload_available']:
                row['payload_512'] = read(payload, 512).hex()
            nodes.append(row)
        result.update(graph_available=True, graph={'container': hex(pointer), 'table': hex(table),
                      'count': count, 'nodes': nodes, 'hardware_unit_semantics_verified': False})
    elif pc == SOURCE:
        result.update(kind='target-resource-source-callback', message_code_raw=registers['r0'],
                      callback_argument1_raw=registers['r1'])
    else:
        values = struct.unpack('<5I', read(0xC180954C, 20))
        library = struct.unpack('<15I', read(0xC1809500, 60))
        contexts = read(0xC1D521C8, 96)
        translation = struct.unpack('<24I', read(0xC1D52268, 96))
        result.update(kind=POINTS[pc], device_handle_raw=values[0],
                      command_dispatch_callback=hex(values[2]), result_dispatch_callback=hex(values[3]),
                      forward_mask_raw=values[4], software_binding_raw_14=struct.pack('<5I', *values).hex(),
                      library_hooks=[hex(v) for v in library[:3]],
                      command_forward_masks_raw=list(library[5:7]),
                      result_translation_masks_raw=list(library[7:15]),
                      result_translation_rows=[list(translation[3*i:3*i+3]) for i in range(8)],
                      command_contexts_raw_60=contexts.hex(),
                      library_contexts=[context(struct.unpack_from('<I', contexts, i*48+0x28)[0])
                                        for i in range(2)],
                      hardware_masks_raw=list(struct.unpack('<3I', read(0x2010000C, 12))),
                      interpretation_of_result_rows_verified=False)
        if pc == REGISTER:
            result.update(proposed_callback=hex(registers['r0']), native_store_observed=False)
        elif pc == REGISTER_STORED:
            result['native_stored_callback_matches_r0'] = values[3] == registers['r0']
        elif pc == MASK:
            result.update(requested_mask_raw=registers['r0'], requested_enable_raw=registers['r1'])
        elif pc == MASK_STORED:
            result['native_stored_mask_matches_r1'] = values[4] == registers['r1']
        elif pc in (ROUTER, DISPATCH):
            result.update(argument0_raw=registers['r0'], argument1_raw=registers['r1'])
    return result


def run(output, card, group23):
    if output.exists():
        raise FileExistsError('Existing evidence is immutable')
    root = Path(__file__).resolve().parents[1]
    image = (root/'artifacts/z62-reference-1.70/master.bin').read_bytes()
    if hashlib.sha256(image).hexdigest() != 'bb83613121f843d65101da936d942acdc513d86dbd3abc26259d0d870d03f5d4':
        raise ValueError('Requires unchanged original C1.70 master')
    for pc, code in ANCHORS.items():
        if image[pc-0x10020000:pc-0x10020000+4].hex() != code:
            raise ValueError('Original result subscription instruction differs at ' + hex(pc))
    profiles = resources.signals.waits.profiles
    baseline = resources.signals.waits.selector.probe.baseline
    build = profiles.hardware.verify_build()
    original_configure = baseline.host.configure_command

    def configure(command, *args, **kwargs):
        command = original_configure(command, *args, **kwargs)
        return profiles.statistics.configure_command(profiles.boundary.configure_command(command, True), True)

    def hit(remote, registers):
        return {'result_subscription': capture(remote, registers)} if registers['pc'] in POINTS else {}

    recorded, stdout = io.StringIO(), sys.stdout

    class RecordOutput:
        def write(self, data):
            recorded.write(data)
            return stdout.write(data)

        def flush(self):
            stdout.flush()

    with patch.object(baseline.host, 'DEFAULT_QEMU', profiles.hardware.DEFAULT_QEMU), \
         patch.object(baseline.host, 'configure_command', configure), \
         patch.object(baseline.route.capture.trace, 'observe_capture', lambda machine: {}), \
         patch.object(baseline.route, 'preview_status', lambda machine: {}), \
         redirect_stdout(RecordOutput()):
        trace, fixture = baseline.run(output, card, group23, True, False, 18,
            extra_points=POINTS, extra_hit_hook=hit, max_stops=2000,
            automatic_shutter=False, wall_limit=1200, observation_timeout_recovery=True)
    with (output/'runtime-stdout.log').open('x', encoding='utf-8') as handle:
        handle.write(recorded.getvalue())
    observations = [{'sequence': h['sequence'], 'guest_seconds': h['state']['virtual_seconds'],
                     'thread': h['thread'], 'registers': h['registers'],
                     'snapshot': h['extra_observation']['result_subscription']}
                    for h in trace['hits'] if 'result_subscription' in h.get('extra_observation', {})]
    result = {'schema': 1, 'profile': VERSION, 'completed_observation': fixture['observation_completed'],
              'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'qemu_sha256': build['binary_sha256'], 'observations': observations,
              'target_guest_seconds': 18, 'runtime_stdout_recorded': True,
              'guest_software_written_by_host': False, 'guest_functions_called_by_host': False,
              'software_event_injected': False, 'hardware_completion_verified': False,
              'mode_recovery_verified': False, 'whole_camera_verified': False, 'camera_accessed': False}
    with (output/'result-subscriptions.json').open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2)
    print(json.dumps({'completed_observation': result['completed_observation'],
                      'subscription_observations': len(observations)}), flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--card', type=Path, required=True)
    parser.add_argument('--group23', type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(0 if run(args.output, args.card, args.group23)['completed_observation'] else 1)
