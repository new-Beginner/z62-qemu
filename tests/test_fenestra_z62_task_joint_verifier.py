"""r16 saved-process evidence tests; no live QEMU or camera access."""
import copy
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'fenestra/z62'))
import verify_task_joint as v


class JointReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records=[json.loads((v.o.OUTPUT/n).read_text()) for n in ('run-3-store.json','run-4-store-repeat.json')]

    def test_two_independent_same_process_chains(self):
        v.require_independent(self.records)
        self.assertEqual([v.check_run(r)['summary']['joint_chains'] for r in self.records],[8,9])
        for r in self.records:
            self.assertFalse(r['task_lifetime_verified'])
            self.assertEqual({x['role'] for x in r['summary']['links']},{'master','slave'})
            self.assertTrue(r['summary']['creations_without_observed_launch'])

    def test_record_errors_are_rejected(self):
        for name,bad in v.mutations(self.records[0]).items():
            with self.subTest(name=name),self.assertRaises((ValueError,KeyError,TypeError,IndexError)):v.check_run(bad)

    def test_observed_word08_store_is_exact_not_a_blanket_exception(self):
        r=self.records[0];events=[e for e in r['events'] if e['phase']=='word08_store']
        self.assertEqual(len(events),2)
        for e in events:
            self.assertEqual(int.from_bytes(bytes.fromhex(e['memory']['updated_object_before'])[8:12],'little'),4)
            self.assertEqual(int.from_bytes(bytes.fromhex(e['updated_object_after'])[8:12],'little'),16)
            bad=copy.deepcopy(r);x=bad['events'][e['sequence']]
            raw=bytearray.fromhex(x['updated_object_after']);raw[4]^=1;x['updated_object_after']=raw.hex()
            with self.assertRaisesRegex(ValueError,'word08 STR'):v.check_run(bad)

    def test_consistent_link_edit_cannot_change_earlier_object(self):
        r=copy.deepcopy(self.records[0]);e=next(e for e in r['events'] if e['phase']=='input' and e.get('creation_index') is not None)
        raw=bytearray.fromhex(e['launch_object']);raw[4]^=1;e['launch_object']=raw.hex()
        r['pairs'][e['pair_index']]['input']=copy.deepcopy(e)
        with self.assertRaisesRegex(ValueError,'without observed original store'):v.check_run(r)

    def test_memory_and_breakpoint_audit_are_exact(self):
        for prefix in ('m','Z1'):
            r=copy.deepcopy(self.records[0]);i=next(i for i,x in enumerate(r['rsp_commands']) if x.startswith(prefix))
            r['rsp_commands'][i]='m10020000,4' if prefix=='m' else 'Z1,10020000,2'
            with self.subTest(prefix=prefix),self.assertRaises(ValueError):v.check_run(r)

    def test_prior_failure_and_duplicate_process_are_not_accepted(self):
        r=json.loads((v.o.OUTPUT/'run-2-repeat.json').read_text())
        self.assertIn('Created object fields changed',r['failure'])
        self.assertTrue(r['owned_process_closed'])
        with self.assertRaises(ValueError):v.check_run(r)
        with self.assertRaises(ValueError):v.require_independent([self.records[0],self.records[0]])


if __name__=='__main__':unittest.main()
