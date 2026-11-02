"""Guard the original lens request layout used by the read-only probe."""
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from trace_z62_lens_control import context


class Remote:
    def __init__(self, payload):
        self.reads = []
        self.data = struct.pack('<7I', 4, 1, 2, 0x103EAE81, 0x800, payload, 0xC0003000)

    def read(self, address, size):
        self.reads.append((address, size))
        if address == 0xC0001000:
            return self.data
        if address == 0xC0002000 and size == 32:
            return bytes(range(32))
        raise AssertionError('Read followed a non-payload word')


class LensObservationTests(unittest.TestCase):
    def test_payload_is_offset_14_not_following_stack_word(self):
        remote = Remote(0xC0002000)
        result = context(remote, {'pc': 0x102F0E1C, 'r0': 0xC0001000})
        self.assertEqual(result['payload_pointer'], '0xc0002000')
        self.assertEqual(remote.reads, [(0xC0001000, 28), (0xC0002000, 32)])

    def test_null_payload_does_not_follow_stack_word(self):
        remote = Remote(0)
        result = context(remote, {'pc': 0x102F0E1C, 'r0': 0xC0001000})
        self.assertNotIn('payload_32', result)
        self.assertEqual(remote.reads, [(0xC0001000, 28)])

    def test_unmapped_descriptor_is_rejected(self):
        remote = Remote(0)
        with self.assertRaises(ValueError):
            context(remote, {'pc': 0x102F0E1C, 'r0': 0x04282014})
        self.assertFalse(remote.reads)


if __name__ == '__main__':
    unittest.main()
