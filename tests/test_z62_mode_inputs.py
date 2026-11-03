from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
import trace_z62_mode_inputs as subject
from test_z62_mode_pipeline_snapshot import fixture


def inputs_fixture():
    memory = fixture(34)
    data = bytearray(0x318)
    struct.pack_into('<2I', data, (0x518-0x508), 1516 << 16, 854 << 16)
    memory.map(0x20068508, data)
    for channel in (0, 1, 3):
        fields = (8, *range(0x50,0x70,4))
        if channel == 0:
            fields += (0x14,0x18,0x3c,0x40,0x44,0x48,0x4c)
        if channel == 3:
            fields += (0x80,)
        for offset in fields:
            memory.map(0x20069800+channel*0x100+offset, bytes(4))
    memory.map(0x20380000, bytes(0x800))
    for address in (0x2006800c,0x20068014,0x20068100,0x20068260,0x20068270):
        memory.map(address,bytes(4))
    return memory


class AdditionalInputReadset(unittest.TestCase):
    def test_other_frontend_does_not_replace_original_formatter(self):
        memory = inputs_fixture()
        memory.map(0x2006951c, struct.pack('<I',1006 << 16))
        value = subject.capture(memory)
        other = bytes.fromhex(value['other_frontend_318'])
        self.assertEqual(struct.unpack_from('<I',other,0x518-0x508)[0] >> 16,1516)
        self.assertEqual(value['raw']['height_field_high16'],1006)
        self.assertFalse(value['other_frontend_semantics_verified'])

    def test_raw_zero_channel_holes_are_not_read(self):
        memory = inputs_fixture()
        subject.capture(memory)
        self.assertNotIn((0x20069824,4), memory.reads)
        self.assertNotIn((0x20069880,4), memory.reads)
        self.assertIn((0x20069808,4), memory.reads)

    def test_extended_paired_tables_are_preserved(self):
        memory = inputs_fixture()
        memory.map(0x20380480, struct.pack('<I',0xf11f7c00))
        value = subject.capture(memory)
        raw = bytes.fromhex(value['paired_raw_800'])
        self.assertEqual(len(raw),0x800)
        self.assertEqual(struct.unpack_from('<I',raw,0x480)[0],0xf11f7c00)


if __name__ == '__main__':
    unittest.main()
