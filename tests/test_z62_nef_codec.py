"""Known Huffman symbols and real source-derived RAW, not an extension-only NEF."""
import hashlib
from io import BytesIO
from pathlib import Path
import struct
import sys
import unittest

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))


class NefCodecTests(unittest.TestCase):
    def setUp(self):
        try:
            import z62_nef_codec as codec
        except ImportError as exc:
            self.fail('The source-derived NEF codec is missing: ' + str(exc))
        self.codec = codec

    def test_zero_differences_use_the_known_six_bit_category_zero_code(self):
        # Category0 = 111110, repeated eight times; then four lookahead bytes.
        raw = np.full((2, 4), 2048, dtype=np.uint16)
        self.assertEqual(self.codec.encode_lossless14(raw), bytes.fromhex('fb ef be fb ef be 00 00 00 00'))

    def test_signed_differences_have_the_known_complement_bit_representation(self):
        raw = np.array([[2048, 2049, 2048, 2050], [2047, 2048, 2049, 2048]], dtype=np.uint16)
        # Independent symbol sequence: 0,+1,0,+1,-1,0,+2,0.
        bits = '111110'+'11111101'+'111110'+'11111101'+'11111100'+'111110'+'11110110'+'111110'
        expected = int(bits, 2).to_bytes(7, 'big') + bytes(4)
        self.assertEqual(self.codec.encode_lossless14(raw), expected)

    def test_non_quad_even_geometry_is_encoded_without_adding_samples(self):
        raw = np.full((6, 10), 2048, dtype=np.uint16)
        result = self.codec.encode_lossless14(raw)
        # 60 six-bit zero symbols, padded to a byte boundary, plus lookahead.
        self.assertEqual(len(result), 45 + 4)

    def test_invalid_samples_and_geometry_are_rejected(self):
        for raw in (np.zeros((2, 4), dtype=float), np.zeros((3, 4), dtype=np.uint16),
                    np.zeros((2, 3), dtype=np.uint16), np.full((2, 4), 16384, dtype=np.uint16)):
            with self.assertRaises(ValueError):
                self.codec.encode_lossless14(raw)

    def test_container_has_actual_compressed_raw_and_nikon_f0_metadata(self):
        raw = np.full((104, 160), 2048, dtype=np.uint16)
        preview = Image.new('RGB', (160, 104), 'red')
        metadata = {'implementation_level': 'C', 'frame_id': 3, 'virtual_time_ns': 100_000_000,
                    'exposure': {'iso': 100, 'shutter_seconds': .008},
                    'lens': {'aperture': 4, 'focal_length_mm': 50}}
        data = self.codec.encode_nef(raw, preview, metadata)
        info = self.codec.inspect_nef(data)
        self.assertEqual((info['width'], info['height'], info['bits'], info['compression']), (160, 104, 14, 34713))
        self.assertTrue(info['linearization'].startswith(b'F0' + struct.pack('<4H', *([2048] * 4))))
        self.assertEqual(data[info['raw_offset']:info['raw_offset']+info['raw_bytes']], self.codec.encode_lossless14(raw))
        self.assertTrue(info['packed_fallback_excluded'])
        preview_bytes = data[info['preview_offset']:info['preview_offset']+info['preview_bytes']]
        self.assertEqual(preview_bytes[6:12], b'Exif\0\0')
        with Image.open(BytesIO(data[info['preview_offset']:info['preview_offset']+info['preview_bytes']])) as image:
            image.load()
            self.assertEqual(image.size, (160, 104))
            import json
            self.assertEqual(json.loads(image.getexif()[270])['frame_id'], 3)


if __name__ == '__main__':
    unittest.main()
