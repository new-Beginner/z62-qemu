from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from z62_backend_packets import decode, registers


def data(*words): return struct.pack('<'+'I'*len(words),*words)


class BackendPacketsTests(unittest.TestCase):
    def test_count_includes_header_and_final_ignores_neighbor_data(self):
        packets,consumed=decode(data(0x11020000,7,0x01030020,8,9,0xdeadbeef))
        self.assertEqual(consumed,20)
        self.assertEqual(registers(packets),{0:7,0x20:8,0x24:9})

    def test_truncated_and_unterminated_streams_rejected(self):
        for raw in (data(0x01030020,8),data(0x11020000,7),b'abc'):
            with self.assertRaises(ValueError): decode(raw)

    def test_invalid_headers_and_out_of_range_writes_rejected(self):
        for header in (0,0x01000000,0x01010000,0x21020000,0x01020001,0x0103fffc):
            with self.assertRaises(ValueError): decode(data(header,0,0))

    def test_budgets_bound_malformed_continuations(self):
        raw=data(0x11020000,1,0x01020004,2)
        with self.assertRaises(ValueError): decode(raw,max_packets=1)
        with self.assertRaises(ValueError): decode(raw,max_words=3)

    def test_repeated_register_writes_keep_last_value(self):
        packets,_=decode(data(0x11020000,1,0x01020000,2))
        self.assertEqual(registers(packets),{0:2})


if __name__=='__main__': unittest.main()
