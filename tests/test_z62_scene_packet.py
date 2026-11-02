"""Independent packed12/RGGB examples and the bounded native scene envelope."""
import hashlib
from pathlib import Path
import struct
import sys
import unittest

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))


class ScenePacketTests(unittest.TestCase):
    def setUp(self):
        try:
            import z62_scene_packet as packet
        except ImportError as exc:
            self.fail('The native scene packet bridge is missing: ' + str(exc))
        self.packet = packet

    def test_white_black_and_rggb_have_independently_known_wire_bytes(self):
        # 1514 samples = 757 pairs, followed by exactly one zero pad byte.
        white_row = bytes.fromhex('ff ff ff') * 757 + b'\0'
        black_row = bytes.fromhex('40 00 04') * 757 + b'\0'
        self.assertEqual(hashlib.sha256(self.packet.encode_raw(Image.new('RGB', (64, 64), 'white'))).digest(),
                         hashlib.sha256(white_row * 1006).digest())
        self.assertEqual(hashlib.sha256(self.packet.encode_raw(Image.new('RGB', (64, 64), 'black'))).digest(),
                         hashlib.sha256(black_row * 1006).digest())
        raw = self.packet.encode_raw(Image.new('RGB', (64, 64), (255, 0, 0)))
        self.assertEqual(raw[:6], bytes.fromhex('ff 0f 04 ff 0f 04'))
        self.assertEqual(raw[2272:2278], bytes.fromhex('40 00 04 40 00 04'))
        self.assertEqual(len(raw), 2_285_632)
        self.assertEqual(raw[2271::2272], bytes(1006))

    def test_header_has_explicit_epoch_sequence_frame_and_virtual_time(self):
        payload = self.packet.make_packet(Image.new('RGB', (64, 64), 'white'),
            epoch=0x62, publish_id=7, frame_id=30, virtual_time_ns=1_000_000_000)
        self.assertEqual(payload[:8], b'Z62S\x01\0\0\0')
        self.assertEqual(struct.unpack_from('<QQQQIIII', payload, 8),
                         (0x62, 7, 30, 1_000_000_000, 1514, 1006, 2272, 2_285_632))
        self.assertEqual(payload[56:88], hashlib.sha256(payload[88:]).digest())
        info, raw = self.packet.parse_packet(payload)
        self.assertEqual((info['epoch'], info['publish_id'], info['frame_id'], info['virtual_time_ns']),
                         (0x62, 7, 30, 1_000_000_000))
        self.assertEqual(raw, payload[88:])

    def test_malformed_packets_and_inconsistent_time_are_rejected(self):
        valid = self.packet.make_packet(Image.new('RGB', (64, 64), 'white'),
            epoch=1, publish_id=1, frame_id=0, virtual_time_ns=0)
        cases = [valid[:-1], valid + b'\0', b'BAD!' + valid[4:]]
        changed = bytearray(valid)
        changed[-2] ^= 1
        cases.append(bytes(changed))
        for offset, value in ((4, 2), (40, 1515), (44, 1007), (48, 2271), (52, 0)):
            changed = bytearray(valid)
            struct.pack_into('<I', changed, offset, value)
            cases.append(bytes(changed))
        # Hash-correct data with a nonzero pad byte is still invalid.
        changed = bytearray(valid)
        changed[88 + 2271] = 1
        changed[56:88] = hashlib.sha256(changed[88:]).digest()
        cases.append(bytes(changed))
        for data in cases:
            with self.assertRaises(ValueError):
                self.packet.parse_packet(data)
        for fields in ({'epoch': True}, {'publish_id': 0}, {'publish_id': True},
                       {'frame_id': 1}, {'virtual_time_ns': -1}):
            args = dict(epoch=1, publish_id=1, frame_id=0, virtual_time_ns=0)
            args.update(fields)
            with self.assertRaises(ValueError):
                self.packet.make_packet(Image.new('RGB', (64, 64)), **args)


if __name__ == '__main__':
    unittest.main()
