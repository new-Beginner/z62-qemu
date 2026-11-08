"""Replay tests of saved original context traces, not native task/flash acceptance."""
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'fenestra/z62'))
import verify_task_context as verifier


class TaskContextVerifierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = json.loads((ROOT / 'analysis/fenestra-z62-tasks-r7/run-1-diagnostic.json').read_text(encoding='utf-8'))

    def test_original_saved_trace_replays(self):
        result = verifier.check_run(self.record)
        self.assertEqual(result['events'], 400)
        self.assertEqual(result['isolated_steps'], 400)
        self.assertTrue(result['guest_target_reached'])
        self.assertFalse(result['firmware_integrated'])
        self.assertFalse(result['complete_task_abi_verified'])

    def test_record_mutations_rejected(self):
        variants = verifier.mutations(self.record)
        self.assertGreaterEqual(len(variants), 16)
        for name, record in variants.items():
            with self.subTest(name=name), self.assertRaises((ValueError, KeyError, TypeError, IndexError)):
                verifier.check_run(record)

    def test_final_raw_frame_is_not_a_stable_task_lifetime(self):
        record = copy.deepcopy(self.record)
        row = record['final_saved']['master'][0]
        raw = bytearray.fromhex(row['frame'])
        raw[72:76] = b'\xff' * 4
        row['frame'] = raw.hex()
        result = verifier.check_run(record)
        self.assertFalse(result['complete_task_abi_verified'])
        self.assertFalse(result['allocator_lifetime_verified'])

    def test_final_tcb_sp_relation_still_required(self):
        record = copy.deepcopy(self.record)
        record['final_saved']['master'][0]['frame_address'] += 4
        with self.assertRaises(ValueError):
            verifier.check_run(record)


if __name__ == '__main__':
    unittest.main()
