"""Fenestra Z62 research fixtures, not a firmware patcher or general ELF packer.

Uses the upstream v1 legacy FxModuleServices entry contract. The local ARM32
ISA/relocation IDs are deliberately distinct from upstream AArch64 IDs.
"""
import hashlib
import struct

VERSION = '0.1.0-dev.1'
UPSTREAM = 'b199dcdfbb0ef536c6269ae5a9d97c376d488b8b'
ISA32 = RELOC32 = 0x62000001
FIRMWARE = bytes.fromhex('bb83613121f843d65101da936d942acdc513d86dbd3abc26259d0d870d03f5d4')
PAGE = 4096


def digest(data):
    return hashlib.sha256(data).digest()


def make_package(code, entry, message, helper, *, bits=32):
    if bits not in (32, 64):
        raise ValueError('Only explicit ARM32 or AArch64 format fixtures')
    if not isinstance(code, bytes) or not 4 <= len(code) <= PAGE:
        raise ValueError('RX fixture must fit one page')
    alignment = 2 if bits == 32 else 4
    if entry < 0 or entry % alignment or entry + alignment > len(code):
        raise ValueError('Entry must be file-backed and ISA aligned')
    if not 0 <= message < len(code) or not 0 <= helper < len(code):
        raise ValueError('Relocation targets must lie in RX data')
    if bits == 32 and not helper & 1:
        raise ValueError('Thumb helper must retain its state bit')
    width = bits // 8
    offset = 128 + 2 * 24 + 2 * 16
    segments = struct.pack('<6I', 0, offset, len(code), PAGE, 5, PAGE)
    segments += struct.pack('<6I', PAGE, offset + len(code), 2 * width, PAGE, 3, PAGE)
    kind = RELOC32 if bits == 32 else 1
    relocations = struct.pack('<IIQ', PAGE, kind, message)
    relocations += struct.pack('<IIQ', PAGE + width, kind, helper)
    body = segments + relocations + code + bytes(2 * width)
    header = bytearray(128)
    header[:8] = b'FENESTRA'
    struct.pack_into('<4I', header, 8, 1, 128, 1, ISA32 if bits == 32 else 1)
    header[24:56] = FIRMWARE
    header[56:88] = digest(body)
    struct.pack_into('<5I', header, 88, 128 + len(body), 2 * PAGE, entry, 2, 2)
    return bytes(header) + body


def cases(package, *, bits=32):
    """Independent expected return codes from the published FxResult enum."""
    result = [('valid', package, digest(package), 0)]

    def changed(name, offset, value, expected=9, *, rehash=True, fmt='<I'):
        data = bytearray(package)
        struct.pack_into(fmt, data, offset, value)
        if rehash:
            data[56:88] = digest(data[128:])
        raw = bytes(data)
        result.append((name, raw, digest(raw), expected))

    changed('wrong-isa', 20, 1 if bits == 32 else ISA32, 3)
    changed('wrong-abi', 16, 99, 3)
    changed('wrong-firmware', 24, 0, 3)
    changed('unknown-format', 8, 4)
    changed('wrong-header-length', 12, 124)
    changed('wrong-package-length', 88, len(package) + 4)
    changed('zero-image', 92, 0)
    changed('image-over-budget', 92, 8193)
    changed('too-many-segments', 100, 9)
    changed('too-many-relocations', 104, 129)
    changed('unsupported-capability', 108, 1, 3)
    changed('reserved-field', 120, 1)
    changed('write-execute', 128 + 16, 7)
    changed('segment-overlap', 152, 0)
    changed('segment-unaligned', 152, 4097)
    changed('file-table-overlap', 128 + 4, 128)
    changed('entry-in-rw', 96, PAGE)
    changed('entry-misaligned', 96, 1)
    changed('relocation-readonly', 176, 0)
    changed('relocation-unaligned', 176, PAGE + 1)
    changed('relocation-foreign-kind', 180, 1 if bits == 32 else RELOC32)
    changed('relocation-outside-image', 184, 8192, fmt='<Q')
    changed('relocation-target-overflow', 184, 1 << 32, fmt='<Q')
    changed('duplicate-relocation', 192, PAGE)
    changed('corrupt-body', len(package) - 1, 0xFF, 10, rehash=False, fmt='<B')
    raw = package[:127]
    result.append(('truncated-header', raw, digest(raw), 1))
    raw = bytearray(package[:140])
    struct.pack_into('<I', raw, 88, len(raw))
    raw[56:88] = digest(raw[128:])
    result.append(('truncated-tables', bytes(raw), digest(raw), 9))
    result.append(('untrusted-package-digest', package, bytes(32), 10))
    return result


def fixtures_header(package, *, bits=32):
    def array(data):
        return ','.join(str(x) for x in data)
    rows = cases(package, bits=bits)
    lines = ['/* Generated test data; no vendor firmware bytes. */',
             'typedef struct { const unsigned char *data; unsigned size; const unsigned char *sha; unsigned expected; } Fixture;',
             'static const unsigned char firmware_identity[32]={' + array(FIRMWARE) + '};']
    for i, (_, data, sha, _) in enumerate(rows):
        lines += [f'static const unsigned char data_{i}[]={{' + array(data) + '};',
                  f'static const unsigned char sha_{i}[32]={{' + array(sha) + '};']
    lines.append('static const Fixture fixtures[]={')
    lines.extend(f'{{data_{i},sizeof(data_{i}),sha_{i},{expected}}},'
                 for i, (_, _, _, expected) in enumerate(rows))
    lines += ['};', '#define FIXTURE_COUNT (sizeof(fixtures)/sizeof(fixtures[0]))']
    return '\n'.join(lines) + '\n'
