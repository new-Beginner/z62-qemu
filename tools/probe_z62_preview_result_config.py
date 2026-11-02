"""Read actual output-unit submit registers and their RAM parameter blocks."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
from unittest.mock import patch

import trace_z62_result_subscriptions as parent

VERSION = '2026.11.02-preview-result-config-r47'
UNITS = ((54, 0x201009E0), (49, 0x20100940), (55, 0x20100BA0))


def configuration(memory):
    def read(address, size):
        data = memory.read(address, size)
        if not isinstance(data, bytes) or len(data) != size:
            raise ValueError('Incomplete physical preview configuration')
        return data
    rows = []
    for unit, address in UNITS:
        raw = read(address, 24)
        words = struct.unpack('<6I', raw)
        pointer = words[4]
        available = 0xC0000000 <= pointer <= 0xE0000000-160
        row = {'physical_unit': unit, 'register_address': hex(address),
               'registers_18': raw.hex(), 'register_words_raw': list(words),
               'parameter_pointer': hex(pointer), 'parameters_available': available,
               'read_only': True, 'hardware_completion_verified': False}
        if available:
            row['parameters_0a0'] = read(pointer, 160).hex()
        rows.append(row)
    return rows


def run(output, card, group23):
    original = parent.capture
    def capture(memory, registers):
        data = original(memory, registers)
        if registers['pc'] == parent.WAIT and data['source_instruction_matches']:
            data['physical_preview_config'] = configuration(memory)
        return data
    with patch.object(parent, 'capture', capture):
        result = parent.run(output, card, group23)
    rows = [{'sequence': x['sequence'], 'guest_seconds': x['guest_seconds'],
             'configuration': x['snapshot']['physical_preview_config']}
            for x in result['observations'] if 'physical_preview_config' in x['snapshot']]
    receipt = {'schema': 1, 'profile': VERSION, 'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               'parent_source_sha256': result['source_sha256'], 'qemu_sha256': result['qemu_sha256'],
               'completed_observation': result['completed_observation'], 'snapshots': rows,
               'snapshots_atomic': False, 'guest_software_written_by_host': False,
               'software_event_injected': False, 'hardware_completion_verified': False,
               'whole_camera_verified': False}
    with (output/'physical-configs.json').open('x', encoding='utf-8') as handle:
        json.dump(receipt, handle, indent=2)
    print(json.dumps({'physical_config_snapshots': len(rows), 'completed_observation': receipt['completed_observation']}), flush=True)
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--card', type=Path, required=True)
    parser.add_argument('--group23', type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(0 if run(args.output, args.card, args.group23)['completed_observation'] else 1)
