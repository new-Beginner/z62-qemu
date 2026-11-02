# SPDX-License-Identifier: GPL-2.0-or-later
# F0 predictor/Huffman encoding adapted from nikon-expeed-lossless.h,
# Copyright (C) 2026 RdWing, GPL-2.0-or-later. Container code is project code.
"""Explicit C-level Nikon F0 lossless14 NEF writer, not the factory codec.

The reference encoder's packed14 transport required width%4. This encoder
takes u16 samples directly and preserves any even CFA geometry. A decoder
must independently verify every sample before an output is accepted.
"""
from copy import deepcopy
from fractions import Fraction
import hashlib
from io import BytesIO
import json
import struct

import numpy as np
from PIL import Image

VERSION = '2026.11.01-nef-codec-r25'
SEEDS = (2048, 2048, 2048, 2048)
COUNTS = (0, 1, 4, 2, 2, 3, 1, 2) + (0,) * 8
CATEGORIES = (7, 6, 8, 5, 9, 4, 10, 3, 11, 12, 2, 0, 1, 13, 14)


def raw_array(raw):
    values = np.asarray(raw)
    if (values.ndim != 2 or values.dtype.kind != 'u' or values.dtype.itemsize != 2 or
            any(n < 2 or n > 16384 or n % 2 for n in values.shape) or
            values.size > 64_000_000 or np.any(values > 16383)):
        raise ValueError('Expected bounded even-geometry u16 CFA samples in 0..16383')
    return values


def fallback_sizes(width, height):
    # Exclude all scalar-size loader shortcuts in pinned LibRaw0.21.4, plus
    # the padded14 ambiguity checked by the existing reference project.
    return {((width + 9) // 10 * 16) * height, width * height * 3 // 2,
            width * height * 3, width * height * 2,
            ((width * 3 // 2 + 15) // 16 * 16) * height,
            ((width * 7 // 4 + 15) // 16 * 16) * height}


def encode_lossless14(raw):
    values = raw_array(raw)
    height, width = values.shape
    difference = values.astype(np.int32)
    difference[:, 2:] -= values[:, :-2]
    difference[:2, :2] -= np.asarray(SEEDS, dtype=np.int32).reshape(2, 2)
    difference[2:, :2] -= values[:-2, :2]
    codes = np.zeros(15, dtype=np.uint32)
    lengths = np.zeros(15, dtype=np.uint8)
    code = index = 0
    for size, count in enumerate(COUNTS, 1):
        for _ in range(count):
            category = CATEGORIES[index]
            codes[category], lengths[category] = code, size
            code += 1
            index += 1
        code <<= 1
    output = bytearray()
    carry = np.empty(0, dtype=np.uint8)
    powers = np.asarray([1 << n for n in range(14)], dtype=np.uint32)
    positions = np.arange(21, -1, -1, dtype=np.uint32)
    flat = difference.reshape(-1)
    for start in range(0, flat.size, 8192):
        delta = flat[start:start + 8192]
        category = np.searchsorted(powers, np.abs(delta), side='right').astype(np.uint32)
        payload = np.where(delta < 0, delta + ((1 << category) - 1), delta).astype(np.uint32)
        word = (codes[category] << category) | payload
        size = lengths[category] + category
        bits = ((word[:, None] >> positions) & 1).astype(np.uint8)
        bits = bits[positions < size[:, None]]
        if carry.size:
            bits = np.concatenate((carry, bits))
        full = bits.size // 8 * 8
        output.extend(np.packbits(bits[:full], bitorder='big').tobytes())
        carry = bits[full:].copy()
    if carry.size:
        output.extend(np.packbits(carry, bitorder='big').tobytes())
    output.extend(bytes(4))  # bounded bit-reader lookahead, not image samples
    while len(output) in fallback_sizes(width, height):
        output.append(0)
    return bytes(output)


def entry(tag, kind, values):
    if kind in (1, 2, 7):
        data = values.encode('ascii') + b'\0' if isinstance(values, str) else bytes(values)
        return tag, kind, len(data), data
    if not isinstance(values, (list, tuple)):
        values = [values]
    if kind in (3, 4):
        return tag, kind, len(values), struct.pack('<' + ('H' if kind == 3 else 'I') * len(values), *values)
    if kind == 5:
        fractions = [Fraction(value).limit_denominator(1_000_000) for value in values]
        return tag, kind, len(values), b''.join(struct.pack('<II', value.numerator, value.denominator) for value in fractions)
    raise ValueError('Unsupported TIFF entry type')


class Tiff:
    def __init__(self):
        self.data = bytearray(b'II*\0' + bytes(4))

    def add(self, data):
        if len(self.data) & 1:
            self.data.append(0)
        offset = len(self.data)
        if offset + len(data) > 0xffffffff:
            raise ValueError('Classic TIFF offset bound exceeded')
        self.data.extend(data)
        return offset

    def ifd(self, entries):
        entries = sorted(entries)
        if len({row[0] for row in entries}) != len(entries):
            raise ValueError('Duplicate TIFF tag')
        offset = self.add(bytes(2 + 12 * len(entries) + 4))
        struct.pack_into('<H', self.data, offset, len(entries))
        for index, (tag, kind, count, data) in enumerate(entries):
            at = offset + 2 + 12 * index
            struct.pack_into('<HHI', self.data, at, tag, kind, count)
            if len(data) <= 4:
                self.data[at + 8:at + 8 + len(data)] = data
            else:
                struct.pack_into('<I', self.data, at + 8, self.add(data))
        return offset

    def finish(self, root):
        struct.pack_into('<I', self.data, 4, root)
        return bytes(self.data)


def exif_first(jpeg):
    """Put the real APP1 Exif segment immediately after SOI, preserving entropy.

    Pillow emits JFIF first. LibRaw's thumbnail API adds its own Exif whenever
    the first segment is not Exif, even if an Exif segment exists later.
    """
    if jpeg[:2] != b'\xff\xd8':
        raise ValueError('Expected JPEG SOI')
    at = 2
    while at + 4 <= len(jpeg) and jpeg[at] == 255 and jpeg[at + 1] != 0xda:
        size = struct.unpack_from('>H', jpeg, at + 2)[0]
        end = at + 2 + size
        if size < 2 or end > len(jpeg):
            raise ValueError('Truncated JPEG segment')
        if jpeg[at + 1] == 0xe1 and jpeg[at + 4:at + 10] == b'Exif\0\0':
            return jpeg[:2] + jpeg[at:end] + jpeg[2:at] + jpeg[end:]
        at = end
    raise ValueError('Capture Exif segment is missing')


def encode_nef(raw, preview, metadata):
    raw = raw_array(raw)
    if metadata.get('implementation_level') != 'C' or not isinstance(preview, Image.Image):
        raise ValueError('Explicit C source metadata and actual preview pixels required')
    height, width = raw.shape
    details = deepcopy(metadata)
    details.update(nef_writer=VERSION, format='NEF', codec='Nikon-F0-lossless14',
                   factory_codec=False, raw_storage_bits=14, raw_width=width, raw_height=height)
    description = json.dumps(details, sort_keys=True, separators=(',', ':'), allow_nan=False)
    if len(description) > 60000:
        raise ValueError('Capture metadata exceeds supported EXIF description size')
    compressed = encode_lossless14(raw)
    jpeg = BytesIO()
    preview_exif = Image.Exif()
    preview_exif[270] = description
    preview_exif[305] = VERSION + ' explicit source C'
    preview.convert('RGB').save(jpeg, format='JPEG', quality=92, subsampling=0, exif=preview_exif)
    jpeg = exif_first(jpeg.getvalue())
    note = Tiff()
    black = int(metadata.get('raw_black_level', 0))
    note_root = note.ifd([entry(0x0001, 7, b'0210'), entry(0x003d, 3, [black] * 4),
                          entry(0x0093, 3, 3), entry(0x0096, 7, b'F0' + struct.pack('<4H', *SEEDS) + b'\0\0')])
    maker = b'Nikon\0\x02\0\0\0' + note.finish(note_root)
    tiff = Tiff()
    raw_offset = tiff.add(compressed)
    preview_offset = tiff.add(jpeg)
    lens, exposure = details.get('lens', {}), details.get('exposure', {})
    exif = [entry(0x9000, 7, b'0232'), entry(0x927c, 7, maker)]
    if 'shutter_seconds' in exposure:
        exif.append(entry(0x829a, 5, exposure['shutter_seconds']))
    if 'iso' in exposure:
        exif.append(entry(0x8827, 3, int(exposure['iso'])))
    if 'aperture' in lens:
        exif.append(entry(0x829d, 5, lens['aperture']))
    if 'focal_length_mm' in lens:
        exif.append(entry(0x920a, 5, lens['focal_length_mm']))
    exif_offset = tiff.ifd(exif)
    raw_ifd = tiff.ifd([entry(254, 4, 0), entry(256, 4, width), entry(257, 4, height),
        entry(258, 3, 14), entry(259, 3, 34713), entry(262, 3, 32803),
        entry(273, 4, raw_offset), entry(277, 3, 1), entry(278, 4, height),
        entry(279, 4, len(compressed)), entry(284, 3, 1),
        entry(33421, 3, [2, 2]), entry(33422, 1, [0, 1, 1, 2])])
    root = tiff.ifd([entry(254, 4, 1), entry(256, 4, preview.width), entry(257, 4, preview.height),
        entry(258, 3, [8, 8, 8]), entry(259, 3, 6), entry(262, 3, 2),
        entry(270, 2, description), entry(271, 2, 'NIKON CORPORATION'),
        entry(272, 2, 'Z62-QEMU C'), entry(274, 3, 1), entry(277, 3, 3),
        entry(305, 2, VERSION + ' explicit synthetic source C'), entry(330, 4, raw_ifd),
        entry(513, 4, preview_offset), entry(514, 4, len(jpeg)), entry(34665, 4, exif_offset)])
    return tiff.finish(root)


def raw14_from_consumed_frame(frame):
    try:
        from .z62_scene_packet import make_packet, WIDTH, HEIGHT, STRIDE
    except ImportError:
        from z62_scene_packet import make_packet, WIDTH, HEIGHT, STRIDE
    metadata = deepcopy(frame.metadata)
    tag = metadata.get('native_scene_source')
    if (metadata.get('implementation_level') != 'C' or not isinstance(tag, dict) or
            metadata.get('frame_id') != tag.get('frame_id') or
            metadata.get('virtual_time_ns') != tag.get('virtual_time_ns') or
            hashlib.sha256(frame.image.convert('RGB').tobytes()).hexdigest() != metadata.get('pixel_sha256')):
        raise ValueError('An owned consumed native frame with matching pixels/tags is required')
    packet = make_packet(frame.image, epoch=tag['epoch'], publish_id=tag['publish_id'],
                         frame_id=tag['frame_id'], virtual_time_ns=tag['virtual_time_ns'])
    if packet[56:88].hex() != tag.get('raw_sha256'):
        raise ValueError('Reconstructed packed12 source differs from the acknowledged RAW payload')
    packed = np.frombuffer(packet[88:], dtype=np.uint8).reshape(HEIGHT, STRIDE)[:, :WIDTH // 2 * 3]
    pairs = packed.reshape(HEIGHT, WIDTH // 2, 3).astype(np.uint16)
    raw = np.empty((HEIGHT, WIDTH), dtype=np.uint16)
    raw[:, 0::2] = pairs[:, :, 0] | ((pairs[:, :, 1] & 15) << 8)
    raw[:, 1::2] = (pairs[:, :, 1] >> 4) | (pairs[:, :, 2] << 4)
    raw <<= 2
    metadata.update(raw_effective_source_bits=12, raw_storage_bits=14, raw_scale=4,
                    raw_black_level=256, raw_white_level=16380,
                    raw14_sha256=hashlib.sha256(raw.astype('<u2').tobytes()).hexdigest(),
                    precision_note='12-bit native samples shifted left two bits; no new sensor precision')
    return raw, metadata


def read_ifd(data, offset, base=0):
    sizes = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 7: 1}
    if not 0 <= offset <= len(data) - 2:
        raise ValueError('IFD pointer outside file')
    count = struct.unpack_from('<H', data, offset)[0]
    if count > 1024 or offset + 2 + 12 * count + 4 > len(data):
        raise ValueError('Invalid TIFF directory size')
    result = {}
    for index in range(count):
        at = offset + 2 + index * 12
        tag, kind, length, pointer = struct.unpack_from('<HHII', data, at)
        if kind not in sizes or tag in result:
            raise ValueError('Unsupported or duplicate TIFF field')
        size = sizes[kind] * length
        start = at + 8 if size <= 4 else base + pointer
        if start + size > len(data):
            raise ValueError('TIFF field extends outside file')
        payload = bytes(data[start:start + size])
        if kind in (3, 4):
            result[tag] = list(struct.unpack('<' + ('H' if kind == 3 else 'I') * length, payload))
        else:
            result[tag] = payload
    return result


def inspect_nef(data):
    if data[:4] != b'II*\0':
        raise ValueError('Little-endian TIFF container required')
    root = read_ifd(data, struct.unpack_from('<I', data, 4)[0])
    raw = read_ifd(data, root[330][0])
    exif = read_ifd(data, root[34665][0])
    maker = exif[0x927c]
    if maker[:14] != b'Nikon\0\x02\0\0\0II*\0':
        raise ValueError('Nikon type2 MakerNote required')
    note = read_ifd(maker, 10 + struct.unpack_from('<I', maker, 14)[0], base=10)
    width, height = raw[256][0], raw[257][0]
    offset, size = raw[273][0], raw[279][0]
    if offset + size > len(data) or root[513][0] + root[514][0] > len(data):
        raise ValueError('RAW or preview outside file')
    return {'width': width, 'height': height, 'bits': raw[258][0], 'compression': raw[259][0],
            'raw_offset': offset, 'raw_bytes': size, 'preview_offset': root[513][0],
            'preview_bytes': root[514][0], 'linearization': note[0x96],
            'description': json.loads(root[270].rstrip(b'\0')),
            'packed_fallback_excluded': size not in fallback_sizes(width, height)}
