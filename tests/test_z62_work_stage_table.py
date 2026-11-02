"""The dispatch message identifies the stage object separately from callback data."""
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


class WorkStageTableTests(unittest.TestCase):
    def api(self):
        try:
            from trace_z62_work_stage_table import capture
        except ImportError as exc:
            self.fail('Live work-stage table snapshot is missing: ' + str(exc))
        return capture

    def rows(self):
        message = bytearray(28)
        struct.pack_into('<4I', message, 12, 0x103D32EF, 0x43080001, 0xC2100000, 0xC2500000)
        stage = bytearray(48)
        struct.pack_into('<II', stage, 0, 0xC2200000, 0xC2BB44F0)
        struct.pack_into('<iI', stage, 0x24, 3, 0x43080001)
        work = bytearray(128)
        struct.pack_into('<I', work, 8, 0xC2300000)
        table = bytearray(240)
        struct.pack_into('<B3xII', table, 0, 1, 0x10260001, 0x10260021)
        struct.pack_into('<B3xII', table, 12, 0, 0, 0x10260041)
        return {(0xC2000000, 28): bytes(message), (0xC2100000, 48): bytes(stage),
                (0xC2200000, 128): bytes(work), (0xC2BB44F0, 240): bytes(table),
                (0xC2300210, 4): struct.pack('<I', 7),
                (0xC1864CD0, 8): b'\x01\x02\x02\0\0\0\0\0'}

    def test_message_stage_object_callback_data_and_each_table_pointer_are_distinct(self):
        row = self.api()(Memory(self.rows()), {'pc': 0x1029A7D4, 'r0': 0xC18649B4, 'r1': 0xC2000000})
        self.assertTrue(row['table_known'])
        self.assertEqual(row['stage_object'], '0xc2100000')
        self.assertEqual(row['callback_data'], '0xc2500000')
        self.assertEqual(row['stage_index'], 3)
        self.assertEqual(len(row['stages']), 20)
        self.assertEqual(row['stages'][0]['flag'], 1)
        self.assertEqual(row['stages'][0]['setup_pointer'], '0x10260001')
        self.assertEqual(row['stages'][1]['setup_pointer'], '0x0')
        self.assertEqual(row['stages'][1]['poll_pointer'], '0x10260041')
        self.assertEqual(row['component_word210'], 7)
        self.assertFalse(row['stage_execution_verified'])

    def test_bad_message_or_short_table_is_never_an_empty_successful_pipeline(self):
        capture = self.api()
        rows = self.rows()
        message = bytearray(rows[(0xC2000000, 28)])
        struct.pack_into('<I', message, 16, 0)
        rows[(0xC2000000, 28)] = bytes(message)
        row = capture(Memory(rows), {'pc': 0x1029A7D4, 'r0': 0xC18649B4, 'r1': 0xC2000000})
        self.assertFalse(row['table_known'])
        rows = self.rows()
        rows[(0xC2BB44F0, 240)] = b'\0'*12
        with self.assertRaises(ValueError):
            capture(Memory(rows), {'pc': 0x1029A7D4, 'r0': 0xC18649B4, 'r1': 0xC2000000})
        with self.assertRaises(ValueError):
            capture(Memory({}), {'pc': 0x1029A7D6, 'r0': 0, 'r1': 0})


if __name__ == '__main__':
    unittest.main()
