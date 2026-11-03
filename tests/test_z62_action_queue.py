"""Bounded snapshots distinguish queue rejection from an assumed mode failure."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))


class ActionQueueTests(unittest.TestCase):
    def api(self):
        import z62_action_queue_console as api
        return api

    def test_queue_order_uses_original_head_and_92_byte_stride(self):
        api=self.api(); header=[0xC2000000,0x100005c,3,2,2,0xC1000000]
        words=[0]*(3*23)
        words[2*23]=0x10322449; words[0]=0x10320019
        row=api.decode_queue(header,words)
        self.assertEqual(row['work_ids_in_order'],['0x10322449','0x10320019'])
        self.assertEqual(row['count'],2)
        self.assertEqual(row['capacity'],3)

    def test_bad_headers_and_incomplete_storage_are_not_empty_queues(self):
        api=self.api()
        for header in ([0,0,0,0,0,0],[0xC2000000,92,60,61,0,0],
                       [0xDFFFFFE0,92,60,1,0,0],[0xC2000000,True,60,0,0,0]):
            with self.assertRaises(ValueError):
                api.queue_layout(header)
        with self.assertRaises(ValueError):
            api.decode_queue([0xC2000000,92,60,1,0,0],[0])

    def test_capture_context_preserves_outstanding_and_deadline(self):
        api=self.api(); words=[0]*40
        words[:8]=[1,0,0x2000000,0x103E7CD1,2,0x800000,999,10100]
        row=api.decode_capture(words)
        self.assertEqual(row['stage'],'0x2000000')
        self.assertEqual(row['outstanding'],'0x800000')
        self.assertEqual(row['deadline'],10100)
        self.assertFalse(row['capture_complete_claimed'])


if __name__=='__main__':
    unittest.main()
