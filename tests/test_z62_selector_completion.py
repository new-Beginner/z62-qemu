"""A gate return, a constructor call and a hardware ACK are different evidence."""
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


class CompletionGateTests(unittest.TestCase):
    def api(self):
        try:
            from trace_z62_selector_completion import capture
        except ImportError as exc:
            self.fail('Missing read-only operation-completion snapshot: ' + str(exc))
        return capture

    def fixed(self):
        context = bytearray(144)
        context[1], context[5] = 8, 0x16
        struct.pack_into('<I', context, 0x78, 1)
        state = bytes([0, 2, 0x12, 0])
        return {(0xC1868A70, 144): bytes(context), (0xC1864CD0, 4): state,
                (0xC23DC970, 4): struct.pack('<i', -2)}

    def operation(self, rows, payload=0xC2400000):
        header = bytearray(0x148)
        header[0xD] = 0x12
        struct.pack_into('<I', header, 0x144, payload)
        rows[(0xC2300000, 0x148)] = bytes(header)
        if payload == 0xC2400000:
            rows[(0xC2402CCE, 1)] = b'\x17'
        return rows

    def test_predicate_return_keeps_operation_payload_global_state_and_signed_count_distinct(self):
        # Wrong pointer chasing or unsigned interpretation would hide a gate mismatch.
        memory = Memory(self.operation(self.fixed()))
        row = self.api()(memory, {'pc': 0x10324498, 'r0': 0, 'r4': 0xC2300000})
        self.assertEqual(row['returned_value'], 0)
        self.assertEqual(row['context']['state'], 8)
        self.assertEqual(row['context']['last_mode'], 0x16)
        self.assertEqual(row['operation']['byte_0d'], 0x12)
        self.assertEqual(row['operation']['payload']['byte_2cce'], 0x17)
        self.assertEqual(row['processor_state']['byte_01'], 2)
        self.assertEqual(row['processor_state']['byte_02'], 0x12)
        self.assertEqual(row['pending_count_i32'], -2)
        self.assertNotIn('acknowledged', row)

    def test_entry_does_not_mistake_old_r0_for_a_return_value(self):
        memory = Memory(self.operation(self.fixed()))
        row = self.api()(memory, {'pc': 0x1032448C, 'r0': 99, 'r4': 0xC2300000, 'r8': 0})
        self.assertEqual(row['entry_r8'], 0)
        self.assertNotIn('returned_value', row)

    def test_alternate_constructor_call_does_not_read_r4_as_an_operation_object(self):
        # At this site R4 is the constructor input; its object layout is unproven.
        row = self.api()(Memory(self.fixed()), {'pc': 0x1032286E, 'r0': 16, 'r4': 0xC2300000})
        self.assertEqual(row['outgoing_control_code'], 16)
        self.assertNotIn('operation', row)
        self.assertNotIn('returned_value', row)

    def test_unknown_pc_invalid_pointer_and_short_reads_never_become_valid_objects(self):
        capture = self.api()
        row = capture(Memory(self.fixed()), {'pc': 0x103244BE, 'r0': 1, 'r4': 0xDFFFFFF0})
        self.assertFalse(row['operation']['available'])
        rows = self.operation(self.fixed(), payload=0xDFFFF000)
        row = capture(Memory(rows), {'pc': 0x103244BE, 'r0': 0, 'r4': 0xC2300000})
        self.assertFalse(row['operation']['payload']['available'])
        rows[(0xC2300000, 0x148)] = b'\0' * 4
        with self.assertRaises(ValueError):
            capture(Memory(rows), {'pc': 0x103244BE, 'r0': 1, 'r4': 0xC2300000})
        with self.assertRaises(ValueError):
            capture(Memory({}), {'pc': 0x103244C2, 'r0': 8, 'r4': 0})


if __name__ == '__main__':
    unittest.main()
