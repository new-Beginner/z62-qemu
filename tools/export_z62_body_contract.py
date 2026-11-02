"""Export C1.70 body-input contracts from identity-checked original firmware.

The route transcription is anchored to scoped Ghidra instruction listings.
Static routing does not imply a photographic feature works or a key was tested.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from prepare_reference_firmware import ROOT, PROFILES

# pin: (debounced state slot, controller summary offset, switch word, bit, name)
# 0803E51C -> 0803D8C8 -> four-byte route header (0803D5FC) -> 10436600.
ROUTES = {
    1: (0x05, 0x0C, 1, 0x08000000, 'RELEASE_MODE'),
    2: (0x1F, 0x44, 1, 0x00000400, 'I'),
    3: (0x20, 0x46, 1, 0x00000001, 'OK'),
    4: (0x0C, 0x21, 0, 0x00000010, 'DOWN'),
    5: (0x0B, 0x20, 0, 0x00000020, 'UP'),
    6: (0x09, 0x1E, 0, 0x00000080, 'RIGHT'),
    7: (0x0A, 0x1F, 0, 0x00000040, 'LEFT'),
    8: (0x1D, 0x40, 1, 0x00000002, 'PLAY'),
    9: (0x1C, 0x3F, 1, 0x00008000, 'MENU'),
    10: (0x23, 0x4F, 2, 0x00100000, 'DISP'),
    18: (0x06, 0x11, 0, 0x00000400, 'EXP_CORRECT'),
    19: (0x07, 0x12, 1, 0x20000000, 'ISO'),
    21: (0x22, 0x48, 1, 0x00000004, 'THUMBNAIL'),
    22: (0x21, 0x47, 1, 0x00000008, 'ZOOM'),
    23: (0x1E, 0x41, 1, 0x00004000, 'DELETE'),
}


def original(role):
    path = ROOT / 'artifacts/z62-reference-1.70' / (role + '.bin')
    data = path.read_bytes()
    member = 'eg1850_mas_01700' if role == 'master' else 'ex1850_012000.bi'
    digest = hashlib.sha256(data).hexdigest()
    if digest != PROFILES['z62']['members'][member][2]:
        raise ValueError('Original firmware identity mismatch: ' + role)
    return data, digest


def recover():
    master, master_sha = original('master')
    controller, controller_sha = original('controller')
    table_address = 0x10938C04
    table = master[table_address - 0x10020000:table_address - 0x10020000 + 96 * 40]
    entries = {}
    for index in range(96):
        entry = table[index * 40:(index + 1) * 40]
        name = entry[:32].split(b'\0', 1)[0].decode('ascii')
        word = index // 32
        reserved, bit = struct.unpack_from('<II', entry, 32)
        if not name.startswith(f'ID_SW{word}_') or reserved or not bit or bit & (bit - 1):
            raise ValueError('Switch-name table layout differs')
        entries[(word, bit)] = {'name': name, 'address': hex(table_address + index * 40)}
    scan = controller[0x4F035:0x4F035 + 22]
    if scan.hex() != '25051f200c0b090a1d1c23191413111206072422211e':
        raise ValueError('Controller scan order differs')
    routes = []
    for pin, (slot, summary_offset, word, bit, suffix) in ROUTES.items():
        named = entries[(word, bit)]
        if named['name'] != f'ID_SW{word}_{suffix}' or slot not in scan:
            raise ValueError('Input route does not match original table')
        routes.append({'pin': pin, 'active_level': 0, 'state_slot': hex(slot),
                       'summary_offset': hex(summary_offset), 'wire_offset': hex(summary_offset + 4),
                       'switch_word': word, 'mask': hex(bit), **named,
                       'static_route_recovered': True, 'runtime_verified': False})
    evidence_files = [
        'analysis/z62-ghidra/controller-expander-r19/' + name + extension
        for name in ('803e51c', '803d8c8', '803d5fc') for extension in ('.c', '.asm')]
    evidence_files += ['analysis/z62-ghidra/input-decoder-r10/10436600.asm',
                       'analysis/z62-ghidra/controller-body-r19/803e360.asm',
                       'analysis/z62-ghidra/controller-body-r19/803e3b8.asm',
                       'analysis/z62-isp-r10/input-descriptors/trace.json']
    return {'schema': 1, 'firmware': 'Z6II C1.70',
            'firmware_sha256': {'master': master_sha, 'controller': controller_sha},
            'name_table_address': hex(table_address), 'name_table_entries': len(entries),
            'scan_order_hex': scan.hex(), 'routes': routes,
            'evidence_sha256': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                                for name in evidence_files},
            'encoder_routes': [
                {'sampler': '0x0803e360', 'port': 'F', 'a_pin': 11, 'b_pin': 14,
                 'state_byte': '0x200186d1', 'summary_offset': '0x7',
                 'wire_offset': '0xb', 'master_counter': '0xc25d6fd0'},
                {'sampler': '0x0803e3b8', 'port': 'E', 'a_pin': 7, 'b_pin': 13,
                 'state_byte': '0x200186d2', 'summary_offset': '0x8',
                 'wire_offset': '0xc', 'master_counter': '0xc25d6fd4'}],
            'encoder_main_sub_identity_verified': False,
            'complete_body_controls': False, 'photo_capture_verified': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = recover()
    with args.output.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2)
    print(json.dumps({'routes': len(result['routes']), 'name_table_entries': result['name_table_entries'],
                      'complete_body_controls': False}))
