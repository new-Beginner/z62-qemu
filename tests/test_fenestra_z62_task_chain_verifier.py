"""r17 saved-run replay and rejection tests; never start a guest or camera."""
import copy
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'fenestra/z62'))
import verify_task_chain as v


class ChainReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records=[json.loads((v.o.OUTPUT/n).read_text()) for n in ('run-1.json','run-2-repeat.json')]

    def test_two_independent_live_record_chains(self):
        v.require_independent(self.records)
        self.assertEqual([v.check_run(r)['summary']['joint_chains'] for r in self.records],[9,10])
        for r in self.records:
            self.assertFalse(r['business_callback_return_verified'])
            self.assertFalse(r['firmware_integrated'])
            self.assertEqual({x['role'] for x in r['summary']['links']},{'master','slave'})
            self.assertTrue(r['summary']['creations_without_observed_launch'])

    def test_record_mutations_are_rejected(self):
        for name,bad in v.mutations(self.records[0]).items():
            with self.subTest(name=name),self.assertRaises((ValueError,KeyError,TypeError,IndexError)):v.check_run(bad)

    def test_actual_push_memory_is_required(self):
        r=copy.deepcopy(self.records[0]);e=next(e for e in r['events'] if e.get('callback',{}).get('stack_write'))
        w=e['callback']['stack_write'];raw=bytearray.fromhex(w['bytes']);raw[0]^=1;w['bytes']=raw.hex()
        with self.assertRaisesRegex(ValueError,'stack effect'):v.check_run(r)

    def test_callback_read_and_two_steps_are_audited(self):
        for kind in ('memory','step','register'):
            r=copy.deepcopy(self.records[0]);e=next(e for e in r['events'] if 'callback' in e)
            if kind=='memory':
                cmd=f'm{e["callback"]["descriptor_address"]:x},8';r['rsp_commands'].remove(cmd)
            elif kind=='step':r['rsp_commands'].remove('vCont;s:'+e['thread'])
            else:r['rsp_commands'].remove('g')
            with self.subTest(kind=kind),self.assertRaises(ValueError):v.check_run(r)

    def test_independent_descriptor_cannot_disagree_with_same_creation(self):
        r=copy.deepcopy(self.records[0]);e=next(e for e in r['events'] if e.get('callback_analysis',{}).get('same_creation_callback_verified'))
        raw=bytearray.fromhex(e['callback']['descriptor']);raw[0]^=1;e['callback']['descriptor']=raw.hex()
        with self.assertRaisesRegex(ValueError,'Same creation callback'):v.check_run(r)

    def test_prior_r16_cannot_substitute_for_callback_evidence(self):
        r=json.loads((v.ROOT/'analysis/fenestra-z62-task-joint-r16/run-3-store.json').read_text())
        with self.assertRaises(ValueError):v.check_run(r)
        with self.assertRaises(ValueError):v.require_independent([self.records[0],self.records[0]])

    def test_scope_remains_bounded_and_no_guest_writes(self):
        for r in self.records:
            self.assertEqual(r['quit_receipt'],{'acknowledged':True});self.assertTrue(r['mapping_removed'])
            self.assertFalse(r['default_completion_logic_disabled'])
            self.assertLessEqual(len(r['creations']),128);self.assertLessEqual(len(r['events']),2048)
            for cmd in r['rsp_commands']:v.allowed_command(cmd)


if __name__=='__main__':unittest.main()
