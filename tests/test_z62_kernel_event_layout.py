"""Reject unbounded or mismatched event CBs rather than invent kernel flags."""
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from z62_kernel_event_layout import resolve, OBJECT


class EventLayoutTests(unittest.TestCase):
    def fixture(self):
        layout={'object':OBJECT,'global_address':0xC1801000,'stride':32,'id_offset':8,
                'attribute_offset':16,'pattern_offset':20}
        address=0xC2000000+(0x111-1)*32
        memory={OBJECT:[0x1000111],0xC1801000:[512,0xC2000000],
                address:[address,address,0x1000111,0,8,0x800000,0,0]}
        class Remote:
            def read(self,address,size):
                values=memory[address]
                return struct.pack('<'+'I'*len(values),*values)
        return layout,memory,Remote(),address

    def test_real_pattern_comes_from_cb_not_opaque_object_word(self):
        layout,memory,remote,address=self.fixture(); row=resolve(remote,layout)
        self.assertEqual(row['identifier'],'0x1000111')
        self.assertEqual(row['control_block'],hex(address))
        self.assertEqual(row['pattern'],'0x800000')
        self.assertEqual(row['pattern_address'],hex(address+20))

    def test_invalid_index_table_and_cb_id_are_rejected(self):
        for mode in ('index','table','id'):
            layout,memory,remote,address=self.fixture()
            if mode=='index': memory[0xC1801000][0]=1
            elif mode=='table': memory[0xC1801000][1]=0x10000000
            else: memory[address][2]=0x1000112
            with self.assertRaises(ValueError): resolve(remote,layout)


if __name__=='__main__': unittest.main()
