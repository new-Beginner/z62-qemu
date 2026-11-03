"""A write trace is ordered attempts, not accepted state or guest time."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))


class MmioWriteTraceTests(unittest.TestCase):
    def api(self):
        try:
            import z62_mmio_write_trace as module
        except ImportError as exc:
            self.fail('Strict MMIO write trace reader is missing: '+str(exc))
        return module

    def line(self, cpu=0):
        return ('123@1793660000.000001:memory_region_ops_write cpu '+str(cpu)+
                " mr 0x10203040 addr 0x20069a18 value 0x1 size 4 name 'nikon-z72-input-config'")

    def test_parses_actual_event_fields_without_treating_prefix_as_virtual_time(self):
        row = self.api().parse_line(self.line())
        self.assertEqual((row['address'], row['value'], row['size']), (0x20069a18, 1, 4))
        self.assertEqual(row['board_view'], 'master')
        self.assertFalse(row['accepted_write_verified'])
        self.assertIsNone(row['qemu_virtual_ns'])

    def test_qtest_minus_one_cpu_remains_unknown_view(self):
        row = self.api().parse_line(self.line(-1))
        self.assertIsNone(row['board_view'])
        self.assertEqual(row['cpu'], -1)

    def test_same_value_writes_are_kept_with_file_line_provenance(self):
        rows = self.api().parse_lines(['unrelated log line', self.line(), self.line()])
        self.assertEqual([r['file_line'] for r in rows], [2, 3])
        self.assertEqual([r['trace_entry'] for r in rows], [1, 2])
        self.assertEqual([r['value'] for r in rows], [1, 1])

    def test_bad_known_event_is_not_silently_dropped(self):
        module = self.api()
        with self.assertRaises(ValueError): module.parse_line('memory_region_ops_write cpu 0 incomplete')
        with self.assertRaises(ValueError): module.parse_line(self.line().replace('value 0x1', 'value 0x100000000'))
        self.assertIsNone(module.parse_line('other trace event'))
