from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))


class GridDeliveryTests(unittest.TestCase):
    def api(self):
        try:
            import trace_z62_grid_delivery as delivery
        except ImportError as exc:
            self.fail('Native bank0 delivery observation is missing: ' + str(exc))
        return delivery

    def test_independent_packed_oracle_and_rows(self):
        delivery = self.api()
        planes = [bytearray(5120) for _ in range(3)]
        # Samples (0, 1), then (4095, 4094). Padding is deliberately nonzero.
        for plane in planes:
            for y in range(40):
                plane[y*128+120:y*128+128] = b'\xa5' * 8
        for c, values in enumerate(((0, 0, 4095, 4095),
                                   (0, 1, 4095, 4094),
                                   (0, 2, 4095, 4093))):
            for x, value in enumerate(values):
                planes[c][x*2:x*2+2] = value.to_bytes(2, 'little')
        actual = delivery.oracle(planes)
        self.assertEqual(len(actual), 3840)
        self.assertEqual(actual[:6], bytes.fromhex('001000ffefff'))
        self.assertEqual(actual[6:], b'\0' * (3840-6))

    def test_out_of_range_source_is_not_a_numerical_reference(self):
        delivery = self.api()
        planes = [bytearray(5120) for _ in range(3)]
        planes[-1][39*128+118:39*128+120] = bytes.fromhex('0010')
        with self.assertRaises(ValueError):
            delivery.oracle(planes)
        with self.assertRaises(ValueError):
            delivery.oracle([b'\0', b'\0', b'\0'])
