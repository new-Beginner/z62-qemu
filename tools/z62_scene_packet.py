"""C-level RGB scene -> experimental RGGB packed12 -> bounded native envelope.

The black/white levels and CFA are the existing r9 preview hypotheses, not
Nikon calibration. Tags identify an external frame; they never signal DMA.
"""
import hashlib
import struct

import numpy as np
from PIL import Image

WIDTH, HEIGHT, STRIDE = 1514, 1006, 2272
SIZE = HEIGHT * STRIDE
HEADER = struct.Struct('<4sIQQQQIIII32s')


def tags(epoch, publish_id, frame_id, virtual_time_ns):
    for value, low, high in ((epoch, 0, (1 << 64) - 1), (publish_id, 1, (1 << 63) - 1),
                             (frame_id, 0, (1 << 63) - 1), (virtual_time_ns, 0, (1 << 63) - 1)):
        if type(value) is not int or not low <= value <= high:
            raise ValueError('Invalid scene epoch/sequence/frame/time tag')
    if frame_id != virtual_time_ns * 30 // 1_000_000_000:
        raise ValueError('Scene frame ID differs from the 30 Hz virtual timeline')


def encode_raw(image):
    if not isinstance(image, Image.Image) or not image.width or not image.height:
        raise ValueError('Expected a nonempty RGB scene image')
    rgb = np.asarray(image.convert('RGB').resize((WIDTH, HEIGHT), Image.Resampling.BILINEAR), dtype=np.float64) / 255
    linear = np.where(rgb <= .04045, rgb / 12.92, ((rgb + .055) / 1.055) ** 2.4)
    values = np.rint(64 + linear * (4095 - 64)).astype(np.uint16)
    samples = np.empty((HEIGHT, WIDTH), dtype=np.uint16)
    samples[0::2, 0::2] = values[0::2, 0::2, 0]
    samples[0::2, 1::2] = values[0::2, 1::2, 1]
    samples[1::2, 0::2] = values[1::2, 0::2, 1]
    samples[1::2, 1::2] = values[1::2, 1::2, 2]
    a, b = samples[:, 0::2], samples[:, 1::2]
    output = np.zeros((HEIGHT, STRIDE), dtype=np.uint8)
    packed = output[:, :WIDTH // 2 * 3]
    packed[:, 0::3] = a & 255
    packed[:, 1::3] = (a >> 8) | ((b & 15) << 4)
    packed[:, 2::3] = b >> 4
    return output.tobytes()


def make_packet(image, *, epoch, publish_id, frame_id, virtual_time_ns):
    tags(epoch, publish_id, frame_id, virtual_time_ns)
    raw = encode_raw(image)
    return HEADER.pack(b'Z62S', 1, epoch, publish_id, frame_id, virtual_time_ns,
                       WIDTH, HEIGHT, STRIDE, SIZE, hashlib.sha256(raw).digest()) + raw


def parse_packet(packet):
    if not isinstance(packet, (bytes, bytearray, memoryview)) or len(packet) != HEADER.size + SIZE:
        raise ValueError('Scene packet length differs from fixed bounded geometry')
    magic, version, epoch, publish_id, frame_id, time_ns, width, height, stride, size, digest = HEADER.unpack_from(packet)
    if (magic, version, width, height, stride, size) != (b'Z62S', 1, WIDTH, HEIGHT, STRIDE, SIZE):
        raise ValueError('Invalid scene packet header')
    tags(epoch, publish_id, frame_id, time_ns)
    raw = bytes(packet[HEADER.size:])
    if hashlib.sha256(raw).digest() != digest or any(raw[STRIDE - 1::STRIDE]):
        raise ValueError('Scene payload checksum or row padding differs')
    return {'epoch': epoch, 'publish_id': publish_id, 'frame_id': frame_id,
            'virtual_time_ns': time_ns, 'raw_sha256': digest.hex()}, raw
