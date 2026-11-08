"""r19 finite queue effects; synthetic edge cases are not guest coverage."""
from pathlib import Path
import struct
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'fenestra/z62'))
import queue_contract as q

class QueueContractTests(unittest.TestCase):
    def test_static_same_original_geometry_both_roles(self):
        c=q.collect()
        for role,start in q.STARTS.items():
            p=c['roles'][role]['queue']
            self.assertEqual(p['start'],start)
            self.assertEqual(p['store'],start+42)
            self.assertEqual(p['nested'],start+60)
            self.assertEqual(p['pop'],start+64)
            self.assertEqual(p['instructions'][-1]['bytes'],'bde8f081')
    def test_indices_and_wrap_slot(self):
        obj=0xc3000000
        for i in (0,1,190,191):
            self.assertEqual(q.slot(obj,i),obj+56+i*264)
            self.assertEqual(q.next_index(i),(i+1)%192)
        for i in (-1,192,2**32,1.5,True):
            with self.subTest(i=i),self.assertRaises(ValueError):q.slot(obj,i)
    def test_ldrd_effect_independent_words(self):
        r={n:0 for n in q.REGISTERS};r.update(pc=0x1038a9b0,cpsr=0x60000033)
        raw=struct.pack('<2I',4,191)
        self.assertEqual(q.load_effect(r,raw),dict(r,r1=4,r0=191,pc=r['pc']+4))
        with self.assertRaises(ValueError):q.load_effect(r,b'\0'*4)
    def test_store_checks_only_original_index_word_changes(self):
        r={n:0 for n in q.REGISTERS};r.update(pc=0x1038a9c6,r1=0)
        before=struct.pack('<2I',5,191);after=struct.pack('<2I',5,0)
        q.check_store(r,dict(r,pc=r['pc']+2),before,after,191)
        for bad in (struct.pack('<2I',4,0),struct.pack('<2I',5,1)):
            with self.assertRaises(ValueError):q.check_store(r,dict(r,pc=r['pc']+2),before,bad,191)
        with self.assertRaises(ValueError):q.check_store(r,dict(r,pc=r['pc']+2,r0=7),before,after,191)
    def test_pop_effect_saved_link_and_isa(self):
        r={n:0 for n in q.REGISTERS};r.update(pc=0x1038a9dc,sp=0xc3001000,cpsr=0x60000033)
        saved=struct.pack('<6I',4,5,6,7,8,0x103a28af)
        a=q.pop_effect(r,saved)
        self.assertEqual(a,dict(r,r4=4,r5=5,r6=6,r7=7,r8=8,pc=0x103a28ae,sp=r['sp']+24))
        saved=struct.pack('<6I',4,5,6,7,8,0x10200000)
        self.assertEqual(q.pop_effect(r,saved)['cpsr'],r['cpsr']&~32)
    def test_pending_summary_does_not_claim_complete(self):
        self.assertFalse(q.local_summary([])['all_observed_outer_calls_returned'])
        self.assertFalse(q.local_summary([])['business_semantics_verified'])
        self.assertFalse(q.local_summary([])['phase1_passed'])

if __name__=='__main__':unittest.main()
