"""Filtered and standard events must not be confused or double counted."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))


class FilteredTraceTests(unittest.TestCase):
    def api(self):
        try: import z62_mmio_filtered_trace as module
        except ImportError as exc: self.fail('Filtered trace reader is missing: '+str(exc))
        return module

    def line(self):
        return "2026-11-03T00:00:00Z nikon_z62_mmio_write cpu 1 mr 0000000012345678 addr 0x20069a18 value 0x1 size 4 name 'nikon-z72-input-config'"

    def test_reads_filtered_event_without_assigning_guest_timestamp(self):
        row = self.api().parse_line(self.line())
        self.assertEqual((row['address'], row['value'], row['board_view']), (0x20069a18, 1, 'master'))
        self.assertIsNone(row['qemu_virtual_ns'])

    def test_standard_event_is_separate_and_malformed_filtered_event_fails(self):
        module = self.api()
        self.assertIsNone(module.parse_line(self.line().replace('nikon_z62_mmio_write', 'memory_region_ops_write')))
        with self.assertRaises(ValueError): module.parse_line('nikon_z62_mmio_write incomplete')
