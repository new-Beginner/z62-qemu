"""Read-only integration replay tests over saved r5 stock observations, not camera tests."""
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'fenestra/z62'))
import verify_heap as m


class HeapVerifierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = json.loads((ROOT / 'analysis/fenestra-z62-heap-r5/run-2-long.json').read_text(encoding='utf-8'))
        cls.contract = m.collect()
        cls.images = m.read_inputs()

    def test_saved_run_is_recomputed_with_release_gap_preserved(self):
        coverage = m.check_run(self.record, self.contract, self.images)
        self.assertEqual(coverage['master']['summary']['allocations'],310)
        self.assertEqual(coverage['slave']['summary']['allocations'],125)
        for p in coverage.values():
            self.assertEqual(p['summary']['release_returns'],0)
            self.assertEqual(p['summary']['exact_pointer_reuses'],0)

    def test_fifteen_altered_receipts_are_rejected(self):
        rejected=m.negative_checks(self.record,self.contract,self.images)
        self.assertEqual(len(rejected),15)
        self.assertEqual(len(set(rejected)),15)

    def test_every_recorded_safety_scope_flag_must_remain_false(self):
        for field in m.FALSE_FIELDS:
            row=copy.deepcopy(self.record)
            row[field]=True
            with self.subTest(field=field),self.assertRaises(ValueError):
                m.check_run(row,self.contract,self.images)

    def test_source_binding_changes_are_rejected(self):
        row=copy.deepcopy(self.record)
        row['sources']['fenestra/z62/heap_calls.py']='0'*64
        with self.assertRaises(ValueError): m.check_run(row,self.contract,self.images)


if __name__ == '__main__':
    unittest.main()
