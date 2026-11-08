"""Pure r16 tooling tests; synthetic matching is not guest lifecycle evidence."""
import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'fenestra/z62'))
import task_joint_contract as t


class JointContractTests(unittest.TestCase):
    def test_original_services_are_distinct(self):
        c=t.collect()
        for p in c['roles'].values():
            self.assertNotEqual(p['start'],p['wrapper']['points']['native_start'])
            self.assertEqual(p['service_table_words'][10],p['wrapper']['points']['native_start'])
            self.assertEqual(p['wrapper']['service_code'],0x800A0200)
        self.assertFalse(c['task_lifetime_verified'])

    def test_joint_mapping_requires_role_handle_tcb_and_time(self):
        create=dict(sequence=0,role='master',initialized={'sequence':10},
                    analysis=dict(control_block=100,handle=7,object_address=200))
        row=dict(sequence=11,role='master',tcb_address=100,registers={'r0':7})
        self.assertEqual(t.creation_for_input([create],row),0)
        for key,value in [('role','slave'),('sequence',9),('tcb_address',101)]:
            bad=copy.deepcopy(row);bad[key]=value
            self.assertIsNone(t.creation_for_input([create],bad))
        bad=copy.deepcopy(row);bad['registers']['r0']=8
        self.assertIsNone(t.creation_for_input([create],bad))

    def test_duplicate_creation_is_not_stable_identity(self):
        a=dict(sequence=0,role='master',initialized={'sequence':1},
               analysis=dict(control_block=100,handle=7,object_address=200))
        b=copy.deepcopy(a);b['sequence']=1
        with self.assertRaises(ValueError):
            t.creation_for_input([a,b],dict(sequence=2,role='master',tcb_address=100,registers={'r0':7}))

    def test_unfinished_creation_cannot_link(self):
        a=dict(sequence=0,role='master',initialized=None)
        self.assertIsNone(t.creation_for_input([a],dict(sequence=2,role='master',tcb_address=100,registers={'r0':7})))

    def test_original_word08_update_is_explicit_not_ignored(self):
        c=t.collect()
        self.assertEqual(c['roles']['master']['joint_points']['word08_store'],0x103DEC90)
        self.assertEqual(c['roles']['slave']['joint_points']['word08_store'],0x1006CC54)

    def test_object_expectation_uses_only_earlier_observed_updates(self):
        s={'initialized':{'sequence':1,'memory':{'object':'11'*32}},
           'updates':[{'sequence':3,'updated_object_after':'22'*32}]}
        self.assertEqual(t.object_at(s,2),bytes.fromhex('11'*32))
        self.assertEqual(t.object_at(s,4),bytes.fromhex('22'*32))


if __name__=='__main__':unittest.main()
