"""Decode the local Z6II C1.70 package; never modify or flash the input."""
import argparse
import binascii
import hashlib
import json
from pathlib import Path
import re
import sys

import numpy as np
from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'third_party/nikon-fw-key-tool'))
import decrypt_firmware as fw

EXPECTED_INPUT = '5a9640b4c07abe1ecbf5a52655cbec6b893bba045bb2a1a1d21055b9f8f9d06d'
XOR_SOURCE = ROOT / 'third_party/nikon-firmware-tools/Nikon-Patch-JS/src/nikon_patch/xor.c'
XOR_SOURCE_SHA256 = 'ef3f8c4fde819c0d9ecbfbf024efa101c00cbb09d88855c16709a42bf212ad3d'
BASE = 0x10020000  # Z6 family hypothesis, not a recovered physical memory map.


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def public_tables(source):
    tables = []
    for index in (1, 2, 3):
        match = re.search(r'Xor_Ord' + str(index) + r'\[\]\s*=\s*\{([^}]+)\}', source)
        if not match:
            raise ValueError(f'Cannot find public XOR table {index}')
        raw = bytes(int(x, 16) for x in re.findall(r'0x([0-9a-fA-F]{2})', match[1]))
        if len(raw) != 256:
            raise ValueError(f'XOR table {index} has {len(raw)} bytes, expected 256')
        tables.append(np.frombuffer(raw, dtype=np.uint8))
    return tables


def decode(raw, tables):
    if len(raw) < 64 or raw[32:64] != b' ' * 32:
        raise ValueError('Not a legacy Nikon upgrade container')
    plain = fw.decrypt(raw, *tables)
    modules = fw.validate_firmware(plain[32:])
    return plain, modules


def disassemble(data, start, size=128):
    offset = start - BASE
    return '\n'.join(
        f'{ins.address:08x}  {ins.bytes.hex():<12} {ins.mnemonic:<9} {ins.op_str}'
        for ins in Cs(CS_ARCH_ARM, CS_MODE_ARM).disasm(data[offset:offset + size], start)
    )


def write_identical_or_new(path, data):
    """Refuse to overwrite any different user output, including symlinks."""
    if path.is_symlink():
        raise ValueError(f'Refusing symlink output: {path}')
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError(f'Refusing to overwrite changed output: {path}')
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(data)


def prepare(input_path, out_dir):
    input_path = input_path.resolve()
    out_dir = out_dir.resolve()
    if input_path.is_relative_to(out_dir):
        raise ValueError('Output directory must not contain the original input')
    raw = input_path.read_bytes()
    if sha256(raw) != EXPECTED_INPUT:
        raise ValueError('This profile requires the verified Z6II C1.70 package SHA-256')
    source = XOR_SOURCE.read_bytes()
    if sha256(source) != XOR_SOURCE_SHA256:
        raise ValueError('Public XOR source changed; review it before using this profile')
    tables = public_tables(source.decode('utf-8'))
    plain, modules = decode(raw, tables)
    files = {'Z6II_C1.70.dec': plain}
    manifest = {
        'profile': 'nikon-z6ii-c1.70', 'lab_version': '0.1.0',
        'input': {'name': input_path.name, 'size': len(raw), 'sha256': sha256(raw)},
        'decoded_sha256': sha256(plain),
        'integrity': {'all_module_crcs': True, 'package_crc': True,
                      'header_signature_verified': False},
        'xor_source': {'repository': 'https://github.com/simeonpilgrim/nikon-firmware-tools',
                       'commit': 'de8019ee30db7fe7bc61e520da289078ae82dcaa',
                       'path': str(XOR_SOURCE.relative_to(ROOT)).replace('\\', '/'),
                       'sha256': sha256(source)},
        'validator': {'repository': 'https://github.com/WonderLantern/nikon-fw-key-tool',
                      'commit': '33426e892afd329a3b366b73776bcf53b9ac4ee8'},
        'imports_equivalent': {
            'format': 'raw embedded modules, not PE/ELF',
            'traditional_import_table': 'not applicable',
            'anchors': 'Validated directory, module prefixes, engine reset instruction, strings',
            'capability_claims': 'No absence-of-network or absence-of-IO claim made'},
        'modules': []}
    for name, offset, length in modules:
        full = plain[32 + offset:32 + offset + length]
        payload = full[:-2]
        filename = name + '.payload.bin'
        entry = {'name': name, 'body_offset': offset, 'file_offset': offset + 32,
                 'module_size_with_crc': length, 'payload_size': len(payload),
                 'payload_sha256': sha256(payload), 'payload_file': filename,
                 'crc16': f'{binascii.crc_hqx(payload, 0):04x}'}
        files[filename] = payload
        if name.startswith('eg1850_'):
            role = 'master' if '_mas_' in name else 'slave'
            reset = list(Cs(CS_ARCH_ARM, CS_MODE_ARM).disasm(payload[:4], BASE))
            if not reset or reset[0].mnemonic != 'b':
                raise ValueError(f'{role} reset is not the expected ARM branch')
            target = int(reset[0].op_str.lstrip('#'), 0)
            if not BASE <= target < BASE + len(payload):
                raise ValueError(f'{role} entry is outside its image')
            entry.update(role=role, candidate_load_base=BASE, candidate_entry=BASE,
                         reset_branch_target=target,
                         address_confidence='family-derived; not a complete hardware map')
            files[f'{role}-entry.asm'] = (
                '; ARM little-endian, candidate base 0x10020000\n'
                + disassemble(payload, BASE, 4) + '\n\n'
                + disassemble(payload, target, 384) + '\n').encode()
            needles = [b'Nikon', b'EXPEED', b'ITRON', b'TOPPERS', b'ThreadX', b'Linux', b'MENU', b'BSP']
            entry['string_anchors'] = {x.decode(): payload.find(x) for x in needles}
            strings = re.finditer(rb'[\x20-\x7e]{7,}', payload)
            matches = []
            for match in strings:
                if re.search(rb'(?i)nikon|menu|assert|itron|expeed|slave|master|cpu[01]|bsp', match[0]):
                    matches.append(f'{BASE + match.start():08x}  {match[0][:240].decode("ascii")}')
                if len(matches) >= 100:
                    break
            files[f'{role}-string-anchors.txt'] = ('\n'.join(matches) + '\n').encode()
        manifest['modules'].append(entry)
    files['manifest.json'] = (json.dumps(manifest, indent=2, ensure_ascii=False) + '\n').encode('utf-8')
    # Preflight every output before writing anything.
    for name, data in files.items():
        target = out_dir / name
        if target.is_symlink() or (target.exists() and target.read_bytes() != data):
            raise ValueError(f'Refusing changed output: {target}')
    for name, data in files.items():
        write_identical_or_new(out_dir / name, data)
    if sha256(input_path.read_bytes()) != EXPECTED_INPUT:
        raise ValueError('Original input changed during preparation')
    print(f'Validated {len(modules)} module CRCs and package CRC; original unchanged.')
    print(f'Output: {out_dir}')
    print('Header signature NOT verified. These outputs are NOT flashable packages.')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=ROOT / 'Z6_2_0170 (1).bin')
    parser.add_argument('--out', type=Path, default=ROOT / 'artifacts/z6ii-1.70')
    args = parser.parse_args()
    try:
        prepare(args.input, args.out)
    except (OSError, ValueError) as exc:
        parser.exit(1, f'error: {exc}\n')


if __name__ == '__main__':
    main()
