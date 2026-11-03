"""Only the proven fixed frames permit a saved-LR interpretation."""
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))


class ControlAnalysisTests(unittest.TestCase):
    def api(self):
        try:
            import z62_statistics_control_analysis as module
        except ImportError as exc:
            self.fail('Bounded control frame analysis is missing: '+str(exc))
        return module

    def snapshot(self, link=0x102388a3):
        words = [0]*16; words[3] = link; words[15] = 0xfffffffd
        return {'pc': '0x1020a832', 'source_instruction_matches': True,
            'write_candidate': {'base_matches': True, 'value': 16},
            'caller': {'known': True, 'kind': 'thumb-bl', 'callsite': '0x1023c610', 'target': '0x1020c820'},
            'stack': {'captured': True, 'raw': struct.pack('<16I', *words).hex()}}

    def test_stop_dispatch_frame_uses_saved_lr_at_twelve_bytes_only(self):
        firmware = (ROOT/'artifacts/z62-reference-1.70/master.bin').read_bytes()
        row = self.api().parent_frames(self.snapshot(), firmware)
        self.assertEqual(row['frames'][0]['saved_lr_offset'], 12)
        self.assertEqual(row['frames'][0]['caller']['callsite'], '0x1023889e')
        self.assertEqual(row['frames'][0]['caller']['target'], '0x1023c5a6')
        self.assertFalse(row['frames'][1]['caller']['known'])
        self.assertFalse(row['complete_call_chain_verified'])

    def test_pointer_to_a_different_call_does_not_authorize_deeper_unwind(self):
        firmware = (ROOT/'artifacts/z62-reference-1.70/master.bin').read_bytes()
        row = self.api().parent_frames(self.snapshot(0x1020ae89), firmware)
        self.assertFalse(row['frames'][0]['expected_target_matches'])
        self.assertEqual(len(row['frames']), 1)
