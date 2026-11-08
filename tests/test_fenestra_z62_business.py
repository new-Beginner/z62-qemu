"""r18 finite contract tests; synthetic records are NOT firmware coverage."""
import copy
from pathlib import Path
import struct
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'fenestra/z62'))
import business_contract as b

class BusinessContractTests(unittest.TestCase):
    def test_original_static_two_kinds_each_role(self):
        c=b.collect()
        self.assertEqual(set(c['roles']),{'master','slave'})
        for p in c['roles'].values():
            self.assertEqual([d['kind'] for d in p['dispatchers']],[1,2])
            for d in p['dispatchers']:
                self.assertEqual(d['instructions'][0]['bytes'],'08b5')
                self.assertEqual(d['setter_instructions'][0]['bytes'],'2de9f041')
    def test_blx_effect_distinguishes_isa_and_link(self):
        r={n:0 for n in b.REGISTERS};r.update(pc=0x1035c95a,cpsr=0x60000033,r1=0x10200001)
        q=b.blx_effect(r,'r1')
        self.assertEqual(q,dict(r,pc=0x10200000,lr=0x1035c95d))
        r['r1']=0x10200000
        self.assertEqual(b.blx_effect(r,'r1')['cpsr'],r['cpsr']&~32)
        for target in (0,0x10200002):
            with self.subTest(target=target),self.assertRaises(ValueError):b.blx_effect(dict(r,r1=target),'r1')
    def test_strd_effect_checks_all_bytes_and_regs(self):
        before=bytes(range(48));r={n:0 for n in b.REGISTERS};r.update(pc=0x1035c974,r6=0x10200001,r7=4)
        after=before[:36]+struct.pack('<2I',r['r6'],r['r7'])+before[44:]
        b.check_store_effect(r,dict(r,pc=r['pc']+4),before,after)
        for pos in (0,35,36,43,44,47):
            bad=bytearray(after);bad[pos]^=1
            with self.subTest(pos=pos),self.assertRaises(ValueError):b.check_store_effect(r,dict(r,pc=r['pc']+4),before,bytes(bad))
        with self.assertRaises(ValueError):b.check_store_effect(r,dict(r,pc=r['pc']+4,r0=1),before,after)
    def test_signature_arguments_not_interchangeable(self):
        r=dict(r0=0x1234,r1=0x10200001,r2=9,r4=0xc3000000,r5=0xc3000020)
        b.check_arguments(r,1,0xc3000000,0x1234,0x10200001)
        r2=dict(r,r0=0xc3000000,r1=0x1234,r2=0x10200001)
        b.check_arguments(r2,2,0xc3000000,0x1234,0x10200001)
        with self.assertRaises(ValueError):b.check_arguments(r2,1,0xc3000000,0x1234,0x10200001)
        with self.assertRaises(ValueError):b.check_arguments(r,2,0xc3000000,0x1234,0x10200001)
    def test_registration_latest_completed_same_role_object_only(self):
        rows=[dict(sequence=1,role='master',kind=1,object_address=4,stored={'sequence':2}),
              dict(sequence=3,role='slave',kind=1,object_address=4,stored={'sequence':4}),
              dict(sequence=5,role='master',kind=1,object_address=4,stored={'sequence':6})]
        self.assertEqual(b.registration_for(rows,'master',1,4,7),2)
        self.assertEqual(b.registration_for(rows,'master',1,4,5),0)
        self.assertIsNone(b.registration_for(rows,'slave',2,4,9))
        rows[2]['stored']=None
        with self.assertRaises(ValueError):b.registration_for(rows,'master',1,4,7)
    def test_bounded_ready_requires_roles_kinds_and_no_pending(self):
        calls=[dict(role='master' if i%2 else 'slave',kind=1 if i%3 else 2,returned={}) for i in range(8)]
        self.assertTrue(b.ready([],calls,8))
        self.assertFalse(b.ready([],calls[:7],8))
        bad=copy.deepcopy(calls);bad[0]['returned']=None
        self.assertFalse(b.ready([],bad,8))
        self.assertFalse(b.ready([{'stored':None}],calls,8))
        self.assertFalse(b.ready([], [dict(x,role='master') for x in calls],8))
        self.assertFalse(b.ready([], [dict(x,kind=1) for x in calls],8))

if __name__=='__main__':unittest.main()
