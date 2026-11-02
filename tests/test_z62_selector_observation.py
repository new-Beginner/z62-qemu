"""Read-only original selector observation at exact, separately verified stops."""
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))


class ReadOnlyMemory:
    def __init__(self, values):
        self.values = values

    def read(self, address, size):
        # A wrong address or size cannot silently produce a plausible snapshot.
        return self.values[(address, size)]


class SelectorObservationTests(unittest.TestCase):
    def api(self):
        try:
            from z62_selector_observation import capture
        except ImportError as exc:
            self.fail('The typed, read-only selector observation is missing: ' + str(exc))
        return capture

    def memory(self, *, current=1, previous=0, changed=1, decoded=1):
        return {(0xC1F7A628, 8): struct.pack('<HHI', current, previous, changed),
                (0xC1F7A746, 2): b'\x01\x00',
                (0xC1F7A77A, 2): b'\x00\x00',
                (0xC25D6FE6, 2): struct.pack('<H', decoded)}

    def test_change_getter_result_and_fixed_input_values_remain_distinct(self):
        row = self.api()(ReadOnlyMemory(self.memory()), {'pc': 0x102A583C, 'r0': 1})
        self.assertEqual(row['stage'], 'after-change-getter')
        self.assertEqual(row['scalar'], {'current': 1, 'previous': 0, 'changed': 1})
        self.assertEqual(row['getter_return'], 1)
        self.assertEqual(row['cached'], {'current': 1, 'previous': 0})

    def test_before_decoder_records_new_wire_and_previous_decoded_value(self):
        values = self.memory(current=0, changed=0, decoded=0)
        payload = bytearray(124)
        payload[0x57] = 1
        values[(0xC25C6230, 124)] = bytes(payload)
        row = self.api()(ReadOnlyMemory(values), {'pc': 0x10436600, 'r0': 0xC25C6230})
        self.assertEqual(row['stage'], 'before-mcu-decode')
        self.assertEqual(row['wire_selector_57'], 1)
        self.assertEqual(row['decoded_master'], 0)
        self.assertEqual(row['scalar']['current'], 0)

    def test_application_input_is_read_from_r0_and_keeps_its_own_values(self):
        values = self.memory()
        application = bytearray(144)
        struct.pack_into('<HHI', application, 0x7C, 7, 6, 1)
        values[(0xC181A600, 144)] = bytes(application)
        row = self.api()(ReadOnlyMemory(values),
                         {'pc': 0x10540246, 'r0': 0xC181A600, 'r1': 0xDEAD0000})
        self.assertTrue(row['application_input']['available'])
        self.assertEqual(row['application_input']['pointer'], '0xc181a600')
        self.assertEqual(row['application_input']['scalar_7c'],
                         {'current': 7, 'previous': 6, 'changed': 1})
        self.assertEqual(row['scalar']['current'], 1)

    def test_null_or_mmio_application_pointer_is_unavailable_without_reading_it(self):
        for pointer in (0, 0x20068000, 0xDFFFFFF0):
            with self.subTest(pointer=pointer):
                row = self.api()(ReadOnlyMemory(self.memory()),
                                 {'pc': 0x10540246, 'r0': pointer})
                self.assertFalse(row['application_input']['available'])

    def test_truncated_memory_and_an_unrelated_stop_cannot_be_valid_snapshots(self):
        capture = self.api()
        with self.assertRaises(ValueError):
            capture(ReadOnlyMemory({}), {'pc': 0x102A583E, 'r0': 1})
        values = self.memory()
        values[(0xC1F7A628, 8)] = b'\x01\x00'
        with self.assertRaises(ValueError):
            capture(ReadOnlyMemory(values), {'pc': 0x102A583C, 'r0': 1})


if __name__ == '__main__':
    unittest.main()
