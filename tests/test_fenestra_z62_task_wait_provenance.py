"""Bounded stock wait-record provenance, not a hardware completion/task ABI test."""
import copy
import json
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'fenestra/z62'))
import task_wait_provenance as wait


class WaitProvenanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = wait.collect()
        cls.record = json.loads((ROOT / 'analysis/fenestra-z62-tasks-r7/run-1-diagnostic.json').read_text(encoding='utf-8'))

    def test_original_role_addresses(self):
        self.assertEqual(self.contract['roles']['master']['bit_test']['entry'], 0x10111410)
        self.assertEqual(self.contract['roles']['master']['linked_receive']['entry'], 0x10112808)
        self.assertEqual(self.contract['roles']['slave']['bit_test']['resume'], 0x10043128)
        self.assertEqual(self.contract['roles']['slave']['linked_receive']['resume'], 0x10044480)

    def test_real_bit_mask_and_receive_records(self):
        rows = [wait.analyze_event(e, self.contract['roles'][e['role']]) for e in self.record['events']]
        kinds = {r['kind'] for r in rows if r['association_verified']}
        self.assertEqual(kinds, {'bit_test', 'linked_receive'})
        self.assertTrue(all(not r['hardware_root_cause_identified'] for r in rows))

    def test_corrupted_saved_argument_is_not_associated(self):
        e = copy.deepcopy(next(e for e in self.record['events'] if e['analysis']['resume_pc_candidate'] == 0x10111754))
        block = bytearray.fromhex(e['tcb'])
        struct.pack_into('<I', block, 0x44, 0)
        e['tcb'] = block.hex()
        r = wait.analyze_event(e, self.contract['roles']['master'])
        self.assertFalse(r['association_verified'])
        self.assertEqual(r['reason'], 'saved-arguments-disagree')

    def test_other_paths_are_not_interpreted_as_wait_record(self):
        e = copy.deepcopy(self.record['events'][0])
        r = wait.analyze_event(e, self.contract['roles'][e['role']])
        self.assertFalse(r['association_verified'])
        self.assertEqual(r['reason'], 'unmapped-resume-path')

    def test_later_snapshot_is_not_processed_as_same_lifetime(self):
        summary = wait.summarize(self.record, self.contract)
        self.assertFalse(summary['task_identity_verified'])
        self.assertFalse(summary['waiting_root_cause_identified'])
        self.assertEqual(summary['event_count'], 400)


if __name__ == '__main__':
    unittest.main()
