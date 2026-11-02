"""Read bank0 port descriptors, address tables and the actual referenced data."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
from unittest.mock import patch

import trace_z62_preview_result_delivery as parent

VERSION = '2026.11.02-bank0-config-r48'


def configuration(memory):
    def read(address, size):
        data = memory.read(address, size)
        if not isinstance(data, bytes) or len(data) != size:
            raise ValueError('Incomplete bank0 configuration or data')
        return data

    def ddr(pointer, size):
        return 0x80000000 <= pointer <= 0x100000000-size

    def sample(pointer, row, scalar):
        size = row*40
        result = {'pointer': hex(pointer), 'row_bytes': row,
                  'available': ddr(pointer, size)}
        if result['available']:
            raw = read(pointer, size)
            result.update(sha256=hashlib.sha256(raw).hexdigest(),
                          prefix_64=raw[:64].hex(), last_row_prefix_64=raw[-row:-row+64].hex())
            if scalar:
                values = [v for y in range(40) for v in struct.unpack_from('<60H', raw, y*row)]
                result.update(minimum_active_u16=min(values), maximum_active_u16=max(values))
        return result

    ports = []
    for address in (0x20100440, 0x20100480):
        raw = read(address, 52)
        ports.append({'address': hex(address), 'raw_34': raw.hex(), 'words': list(struct.unpack('<13I', raw))})
    raw_table = read(0x20102200, 256)
    table = struct.unpack('<64I', raw_table)
    unit_raw = read(0x201009C0, 24)
    unit = struct.unpack('<6I', unit_raw)
    result = {'read_only': True, 'hardware_direction_semantics_verified': False,
              'bank0_control_raw': struct.unpack('<I',read(0x20102000,4))[0],
              'bank0_command_words_raw': list(struct.unpack('<3I',read(0x20102640,12))),
              'ports': ports, 'address_table_100': raw_table.hex(),
              'unit53_registers_18': unit_raw.hex(), 'unit53_words_raw': list(unit),
              'frames': []}
    if ddr(unit[4],160):
        result['unit53_parameters_0a0'] = read(unit[4],160).hex()
    source, target = ports[0]['words'], ports[1]['words']
    supported = (source[8] == target[8] == 0x28003C and source[4] == 128 and target[4] == 96)
    result['observed_data_layout'] = supported
    if supported:
        for slot in range(4):
            address, output = table[slot*16+1],table[slot*16+2]
            delta = address-0x88EDF000
            index = delta//0x36000 if delta >= 0 and delta%0x36000 == 0 and delta//0x36000 < 6 else None
            result['frames'].append({'slot': slot, 'continuous_rgb_slot': index,
                'input_planes': [sample(address+offset,128,True) for offset in (0,source[10],source[11])],
                'packed_output': sample(output,96,False)})
    return result


def run(output, card, group23, qemu):
    original = parent.subscriptions.capture
    def capture(memory, registers):
        data = original(memory, registers)
        if registers['pc'] == parent.subscriptions.WAIT and data['source_instruction_matches']:
            data['bank0_configuration'] = configuration(memory)
        return data
    with patch.object(parent.subscriptions, 'capture', capture):
        result = parent.run(output, card, group23, qemu, 12)
    snapshots = [{'sequence': x['sequence'], 'guest_seconds': x['guest_seconds'],
                  'configuration': x['snapshot']['bank0_configuration']}
                 for x in result['observations'] if 'bank0_configuration' in x['snapshot']]
    receipt = {'schema': 1, 'profile': VERSION, 'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               'parent_source_sha256': result['source_sha256'], 'qemu_sha256': result['qemu_sha256'],
               'completed_observation': result['completed_observation'], 'snapshots': snapshots,
               'snapshots_atomic': False, 'software_event_injected': False,
               'guest_software_written_by_host': False, 'bank0_numerical_graph_executed': False}
    with (output/'bank0-config.json').open('x',encoding='utf-8') as handle:
        json.dump(receipt,handle,indent=2)
    print(json.dumps({'bank0_config_snapshots': len(snapshots),
                      'completed_observation': receipt['completed_observation']}),flush=True)
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--card',type=Path,required=True)
    parser.add_argument('--group23',type=Path,required=True)
    parser.add_argument('--qemu',type=Path,default=parent.host.DEFAULT_QEMU)
    args=parser.parse_args()
    raise SystemExit(0 if run(args.output,args.card,args.group23,args.qemu.resolve())['completed_observation'] else 1)
