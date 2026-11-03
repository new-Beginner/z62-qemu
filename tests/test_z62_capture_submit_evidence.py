"""A reachable return site cannot fabricate a measured original call result."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from verify_z62_capture_submit_evidence import pair_preparation


class CaptureEvidenceTests(unittest.TestCase):
    def hit(self, seq, label, ns, sp='0xc2000000'):
        return {'sequence': seq, 'label': label, 'virtual_time_ns': ns, 'packet_index': 0,
                'thread': '02', 'registers': {'sp': sp, 'r0': '0x0', 'r1': '0x5', 'r2': '0x0', 'r3': '0x64'}}

    def test_unpaired_return_is_preserved_and_not_counted_as_a_wait(self):
        row = pair_preparation({'hits': [self.hit(1,'frame-event8-return', 1),
            self.hit(2,'frame-event15-call', 100), self.hit(3,'frame-event15-return', 200)]})
        self.assertEqual(len(row['pairs']), 1)
        self.assertEqual(row['pairs'][0]['duration_ns'], 100)
        self.assertEqual(row['unpaired_return_sites'], [{'sequence': 1, 'label': 'frame-event8-return'}])

    def test_different_stack_cannot_close_a_pending_wait(self):
        row = pair_preparation({'hits': [self.hit(1,'input-ready-wait-call', 100),
            self.hit(2,'input-ready-wait-return', 200, '0xc2000100')]})
        self.assertFalse(row['pairs'])
        self.assertEqual(row['unreturned_calls'], [1])


if __name__ == '__main__':
    unittest.main()
