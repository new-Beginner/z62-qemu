"""r17 contract unit tests; saved r11 inputs are tooling fixtures, not r17 runs."""
import copy
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'fenestra/z62'))
import task_chain_contract as t


class ChainContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c=t.collect()
        r=json.loads((t.ROOT/'analysis/fenestra-z62-task-callback-r11/run-1-final.json').read_text())
        cls.e=next(e for e in r['events'] if 'callback' in e)

    def test_static_shared_bx_and_limits(self):
        self.assertEqual(t.CAP,128);self.assertEqual(t.EVENT_CAP,2048)
        for p in self.c['roles'].values():self.assertEqual(p['shared_bytes'],'49680847')
        self.assertFalse(self.c['business_callback_return_verified'])

    def test_original_callback_fixture_effects(self):
        a=t.check_callback(self.e,self.c['roles'][self.e['role']])
        self.assertTrue(a['target_first_instruction_verified'])
        self.assertFalse(a['business_callback_return_verified'])

    def test_independent_descriptor_agrees_with_same_creation(self):
        e=copy.deepcopy(self.e);p=self.c['roles'][e['role']]
        e['launch_object']=e['callback']['descriptor']+'00'*24
        a=dict(object_address=e['registers']['r1'],callback=e['after_registers']['r1'])
        self.assertTrue(t.check_callback(e,p,a)['same_creation_callback_verified'])
        a['callback']^=2
        with self.assertRaisesRegex(ValueError,'creation callback'):t.check_callback(e,p,a)

    def test_consistently_changed_field_cannot_ignore_object_read(self):
        e=copy.deepcopy(self.e);p=self.c['roles'][e['role']]
        e['launch_object']='00'*32
        a=dict(object_address=e['registers']['r1'],callback=e['after_registers']['r1'])
        with self.assertRaises(ValueError):t.check_callback(e,p,a)

    def test_bx_and_actual_stack_not_just_pc(self):
        for field in ('after_bx','after_target'):
            e=copy.deepcopy(self.e);e['callback'][field]['r0']^=1
            with self.subTest(field=field),self.assertRaises(ValueError):t.check_callback(e,self.c['roles'][e['role']])

    def test_target_system_is_checked(self):
        e=copy.deepcopy(self.e);e['callback']['after_system']['DFSR_S']=1
        with self.assertRaises(ValueError):t.check_callback(e,self.c['roles'][e['role']])


if __name__=='__main__':unittest.main()
