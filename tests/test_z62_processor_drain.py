"""Observe stop prerequisites without treating empty queues as completion."""
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))


class Memory:
    def __init__(self, rows):
        self.rows = rows

    def read(self, address, size):
        return self.rows[(address, size)]


class ProcessorDrainTests(unittest.TestCase):
    def api(self):
        try:
            import trace_z62_processor_drain as api
        except ImportError as exc:
            self.fail('Read-only processor stop prerequisites are missing: ' + str(exc))
        return api

    def rows(self):
        control = bytearray(0xA0)
        control[:6] = bytes([1, 4, 29, 0, 2, 2])
        lists = bytearray(0x140)
        for offset, count in [(0, 9), (0x20, 8), (0xE0, 0), (0x100, 2), (0x120, 3)]:
            struct.pack_into('<I', lists, offset+8, count)
        return {(0xC1864CD0, 0xA0): bytes(control), (0xC237A794, 0x140): bytes(lists)}

    def test_stop_flag_and_each_pending_list_keep_their_independent_values(self):
        row = self.api().snapshot(Memory(self.rows()))
        self.assertEqual(row['state'], 4)
        self.assertEqual(row['mode'], 29)
        self.assertEqual(row['pending_stop'], 2)
        self.assertEqual(row['prior_mode'], 2)
        self.assertEqual(row['lists']['0xc237a874']['count'], 0)
        self.assertEqual(row['lists']['0xc237a894']['count'], 2)
        self.assertEqual(row['lists']['0xc237a8b4']['count'], 3)
        self.assertEqual(row['lists']['0xc237a794']['count'], 9)
        self.assertEqual(row['lists']['0xc237a7b4']['count'], 8)
        self.assertFalse(row['three_stop_lists_empty'])
        self.assertFalse(row['stop_flag_zero'])
        self.assertNotIn('completed', row)

    def test_short_control_or_queue_region_does_not_report_zero_pending(self):
        api = self.api()
        for target in [(0xC1864CD0, 0xA0), (0xC237A794, 0x140)]:
            rows = self.rows()
            rows[target] = rows[target][:-4]
            with self.subTest(target=target), self.assertRaises(ValueError):
                api.snapshot(Memory(rows))

    def test_native_notify_keeps_observed_object_and_bits_and_rejects_other_pcs(self):
        api = self.api()
        row = api.capture(Memory(self.rows()), {'pc': 0x103D2ED4, 'r0': 0xC237A754, 'r1': 0x8000})
        self.assertEqual(row['notify_object'], '0xc237a754')
        self.assertEqual(row['notify_bits'], 0x8000)
        self.assertFalse(row['stop_flag_zero'])
        with self.assertRaises(ValueError):
            api.capture(Memory({}), {'pc': 0x103D2ED2, 'r0': 0, 'r1': 0})


if __name__ == '__main__':
    unittest.main()
