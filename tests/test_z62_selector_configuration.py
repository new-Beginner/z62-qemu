"""Keep requested configuration, retained state and control codes distinct."""
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))


class Memory:
    def __init__(self, rows):
        self.rows = rows

    def read(self, address, size):
        return self.rows[(address,size)]


class ConfigurationSnapshotTests(unittest.TestCase):
    def api(self):
        try:
            from trace_z62_selector_configuration import capture
        except ImportError as exc:
            self.fail('The read-only configuration/control snapshot is missing: '+str(exc))
        return capture

    def context(self, *, ready=3, current=0xC2200000, active=0xC2300000):
        data = bytearray(144)
        data[1],data[3] = 3,0x11
        struct.pack_into('<I',data,0x78,ready)
        struct.pack_into('<II',data,0x88,current,active)
        return bytes(data)

    def test_apply_before_distinguishes_argument_from_old_current_block(self):
        old,new,operation = bytearray(32),bytearray(32),bytearray(16)
        old[0],old[0x18] = 3,0
        new[0],new[0x18] = 3,1
        operation[0xC] = 4
        memory = Memory({(0xC1868A70,144):self.context(),(0xC2200000,32):bytes(old),
                         (0xC2100000,32):bytes(new),(0xC2300000,16):bytes(operation)})
        row = self.api()(memory,{'pc':0x103226AE,'r0':0xC2100000})
        self.assertEqual(row['ready_join'],3)
        self.assertEqual(row['argument']['byte_18'],1)
        self.assertEqual(row['current']['byte_18'],0)
        self.assertEqual(row['active_operation']['flags_0c'],4)

    def test_apply_return_is_a_code_and_never_reads_a_released_argument(self):
        old = bytearray(32)
        old[0x18] = 1
        memory = Memory({(0xC1868A70,144):self.context(ready=1,active=0),
                         (0xC2200000,32):bytes(old)})
        row = self.api()(memory,{'pc':0x103226B2,'r0':0x11,'r7':0xC2100000})
        self.assertEqual(row['returned_control_code'],17)
        self.assertEqual(row['ready_join'],1)
        self.assertNotIn('argument',row)
        self.assertFalse(row['active_operation']['available'])
        after = self.api()(memory,{'pc':0x103226BA,'r0':0xC1868A70,'r7':0xC2100000})
        self.assertEqual(after['r0_after_control_update'],0xC1868A70)
        self.assertNotIn('returned_control_code',after)

    def test_invalid_pointers_stops_and_short_reads_cannot_be_valid_headers(self):
        capture = self.api()
        memory = Memory({(0xC1868A70,144):self.context(current=0x20068000,active=0xDFFFFFF8)})
        row = capture(memory,{'pc':0x103226BA,'r0':0})
        self.assertFalse(row['current']['available'])
        self.assertFalse(row['active_operation']['available'])
        with self.assertRaises(ValueError):
            capture(Memory({}),{'pc':0x103226B4,'r0':0})
        with self.assertRaises(ValueError):
            capture(Memory({(0xC1868A70,144):b'\0'*4}),{'pc':0x103226BA,'r0':0})


if __name__=='__main__':
    unittest.main()
