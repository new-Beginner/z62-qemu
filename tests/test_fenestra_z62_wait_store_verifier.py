"""Replay real wait-store traces; tampered records are tool tests only."""
import copy
import json
from pathlib import Path
import sys
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'fenestra/z62'))
import verify_wait_store as verifier


class WaitStoreVerifierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = [json.loads((ROOT/'analysis/fenestra-z62-wait-store-r8'/n).read_text(encoding='utf-8'))
                       for n in ('run-1-diagnostic.json','run-2-extended.json')]

    def test_both_saved_original_runs(self):
        for record, size in zip(self.records, (128,512)):
            result = verifier.check_run(record)
            self.assertEqual(result['events'],size)
            self.assertFalse(result['firmware_integrated'])
            self.assertFalse(result['wait_registration_completed'])

    def test_twenty_record_mutations_rejected(self):
        variants = verifier.mutations(self.records[0])
        self.assertGreaterEqual(len(variants),20)
        for name, bad in variants.items():
            with self.subTest(name=name), self.assertRaises((ValueError,KeyError,TypeError,IndexError)):
                verifier.check_run(bad)

    def test_same_pid_is_not_independent(self):
        verifier.require_independent([self.records[0],self.records[1]])
        with self.assertRaises(ValueError):
            verifier.require_independent([self.records[0],self.records[0]])

    def test_target_not_reached_cannot_be_accepted(self):
        record = copy.deepcopy(self.records[0]);record['guest_target_reached'] = False
        with self.assertRaises(ValueError):
            verifier.check_run(record)


if __name__ == '__main__':
    unittest.main()
