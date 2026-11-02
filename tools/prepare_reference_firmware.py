"""Extract pinned C1.70 complete members for reference QEMU experiments.

No image modification, signature claim, NOR generation, camera IO or flashing.
Unlike .payload.bin outputs, these files retain their original CRC trailer.
"""
import argparse
import binascii
import json
from pathlib import Path

from prepare_firmware import (ROOT, XOR_SOURCE, XOR_SOURCE_SHA256, decode,
                              public_tables, sha256, write_identical_or_new)

PROFILES = {
    'z72': {
        'input': 'Z72-fireware/Z7_2_0170.bin',
        'sha256': 'fc0e94f57500a1f0e287c6b9a036c81a5ffceccb8432a377d645b3fa35a19b6a',
        'members': {
            'eg1840_mas_01700': ('master.bin', 38239098, '478caf02dba41fa9144c0c4b6e1a051dc556d40e51a79a308bdd1169efb9dbbe'),
            'eg1840_sla_01700': ('slave.bin', 8834370, 'e0d2589cf036bbf8ce6e4c32f5f2bab61fe35e863660bf6a0ee8082d8a64e1bb'),
            'ex1840_013000.bi': ('controller.bin', 524290, 'cb10af00b9485567453d448020892836ea48637bd638f4cf7cc1c9777a128a9a'),
        },
    },
    'z62': {
        'input': 'Z6_2_0170 (1).bin',
        'sha256': '5a9640b4c07abe1ecbf5a52655cbec6b893bba045bb2a1a1d21055b9f8f9d06d',
        'members': {
            'eg1850_mas_01700': ('master.bin', 38750138, 'bb83613121f843d65101da936d942acdc513d86dbd3abc26259d0d870d03f5d4'),
            'eg1850_sla_01700': ('slave.bin', 8832194, '3fd8c2cbdf57fadb03f6d69b596b58a8703efdd61ae82572d5afeea0241a9ed5'),
            'ex1850_012000.bi': ('controller.bin', 524290, '9c65cad554ed02f83d37fbc825a8eb9efe79e3f32f98894dd5dd73edee416983'),
        },
    },
}


def prepare(profile, input_path=None, destination=None):
    spec = PROFILES[profile]
    source = (input_path or ROOT / spec['input']).resolve()
    out = (destination or ROOT / 'artifacts' / f'{profile}-reference-1.70').resolve()
    if source.is_relative_to(out):
        raise ValueError('Output must not contain the original input')
    original = source.read_bytes()
    if sha256(original) != spec['sha256']:
        raise ValueError('Wrong original firmware identity')
    xor_source = XOR_SOURCE.read_bytes()
    if sha256(xor_source) != XOR_SOURCE_SHA256:
        raise ValueError('Public decoder source changed')
    plain, modules = decode(original, public_tables(xor_source.decode('utf-8')))
    records, files = [], {}
    seen = set()
    for name, offset, length in modules:
        if name not in spec['members']:
            continue
        if name in seen:
            raise ValueError('Duplicate firmware member')
        seen.add(name)
        filename, expected_size, expected_sha = spec['members'][name]
        data = plain[32 + offset:32 + offset + length]
        if len(data) != expected_size or sha256(data) != expected_sha or binascii.crc_hqx(data, 0):
            raise ValueError('Complete member identity/CRC mismatch: ' + name)
        files[filename] = data
        records.append({'member': name, 'file': filename, 'size': len(data),
                        'sha256': sha256(data), 'crc_trailer_preserved': True})
    if seen != set(spec['members']):
        raise ValueError('Missing required firmware member')
    manifest = {'profile': profile, 'firmware_version': 'C1.70',
                'input': {'file': source.name, 'size': len(original), 'sha256': sha256(original)},
                'integrity': {'all_module_crcs': True, 'package_crc': True,
                              'header_signature_verified': False},
                'modules': records, 'nor_or_factory_parameters_included': False,
                'scope': 'Original complete members for offline emulation, NOT a flashable custom package.'}
    files['manifest.json'] = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    # Preflight all outputs, refusing different existing files and symlinks.
    for name, data in files.items():
        path = out / name
        if path.is_symlink() or (path.exists() and path.read_bytes() != data):
            raise ValueError('Refusing changed output: ' + str(path))
    for name, data in files.items():
        write_identical_or_new(out / name, data)
    if sha256(source.read_bytes()) != spec['sha256']:
        raise ValueError('Original input changed during extraction')
    print(f'{profile}: 3 pinned complete members verified, all container/member CRCs passed; original unchanged.')
    print(f'Output: {out}; signature NOT verified; NOR/factory parameters NOT supplied.')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('profile', choices=PROFILES)
    parser.add_argument('--input', type=Path)
    parser.add_argument('--destination', type=Path)
    args = parser.parse_args()
    prepare(args.profile, args.input, args.destination)


if __name__ == '__main__':
    main()
