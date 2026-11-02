"""Bounds and protocol separation for original CPU memory observations."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from trace_z62_upper_waits import memory_watch_address, validate_memory_watches


class MemoryObservationTests(unittest.TestCase):
    def test_read_packet_is_not_a_write(self):
        self.assertEqual(memory_watch_address('T05rwatch:88edf000;thread:01;', {0x88EDF000}, 'read'), 0x88EDF000)
        self.assertIsNone(memory_watch_address('T05rwatch:88edf000;thread:01;', {0x88EDF000}, 'write'))

    def test_read_target_must_be_armed(self):
        with self.assertRaises(RuntimeError):
            memory_watch_address('T05thread:01;rwatch:88edf004;', {0x88EDF000}, 'read')

    def test_statistics_aliases_and_old_write_range(self):
        self.assertEqual(validate_memory_watches({}, {0x88EDF000: 8, 0xC8EDF000: 8}, None)[1], 'read')
        self.assertEqual(validate_memory_watches({0xC293D2A8: 4}, {}, None)[1], 'write')
        with self.assertRaises(ValueError):
            validate_memory_watches({0x88EDF000: 8}, {}, None)

    def test_mixed_and_call_frame_observations_rejected(self):
        for writes, reads, window in (({0xC293D2A8: 4}, {0x88EDF000: 8}, None),
                                     ({}, {0x88EDF000: 8}, {'entry': 1})):
            with self.assertRaises(ValueError):
                validate_memory_watches(writes, reads, window)

    def test_io_overflow_alignment_and_non_integer_bounds(self):
        for address, size in ((0x20068210, 4), (0x8AFFFFFC, 8), (0x88EDF002, 4),
                              (0x88EDF000, 16), (0x88EDF000, True), ('88edf000', 4)):
            with self.assertRaises(ValueError):
                validate_memory_watches({}, {address: size}, None)


if __name__ == '__main__':
    unittest.main()
