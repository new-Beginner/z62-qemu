"""Validate RSP write-stop recognition independently of guest semantics."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from trace_z62_upper_waits import write_watch_address


class WriteObservationTests(unittest.TestCase):
    def test_native_qemu_stop(self):
        self.assertEqual(write_watch_address('T05thread:02;watch:c293d2a8;', {0xC293D2A8}), 0xC293D2A8)

    def test_watch_field_first(self):
        self.assertEqual(write_watch_address('T05watch:c293d2a8;thread:02;', {0xC293D2A8}), 0xC293D2A8)

    def test_execution_stop_has_no_write_address(self):
        self.assertIsNone(write_watch_address('T05thread:01;', {0xC293D2A8}))

    def test_unregistered_address_rejected(self):
        with self.assertRaises(RuntimeError):
            write_watch_address('T05thread:02;watch:c293d2a0;', {0xC293D2A8})


if __name__ == '__main__':
    unittest.main()
