"""r19 fresh real traces: finite natural returns are not complete Fenestra acceptance."""
import copy
import json
from pathlib import Path
import struct
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'fenestra/z62'))
import verify_queue as v
from startup_contract import ROOT
from verify_task_create import require_independent

class QueueVerifierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records=[json.loads((ROOT/'analysis/fenestra-z62-queue-r19'/n).read_text(encoding='utf-8'))
            for n in ('run-1.json','run-2-repeat.json')]
    def test_two_real_windows_natural_returns_but_not_port(self):
        for r in self.records:
            s=v.check_run(r);self.assertEqual(s['events'],45)
            self.assertEqual((s['summary']['outer_calls'],s['summary']['nested_returned'],s['summary']['popped'],s['summary']['outer_returned']),(5,5,5,5))
            self.assertEqual(s['summary']['pending'],[])
            self.assertTrue(s['local_queue_window_replayed']);self.assertFalse(s['full_port_passed'])
            for n in ('phase1_passed','phase2_entered','physical_gate_open','absolute_safety_verified','business_semantics_verified'):
                self.assertFalse(s[n])
            for c in r['calls']:
                self.assertEqual(len(c['loads']),2);self.assertEqual(len(c['stores']),1)
                self.assertEqual(struct.unpack('<2I',bytes.fromhex(c['loads'][-1]['memory']['indices']))[0],
                    struct.unpack('<2I',bytes.fromhex(c['loads'][-1]['memory']['indices']))[1])
                self.assertEqual(c['popped']['after_registers']['pc'],r['contract']['roles'][c['role']]['queue']['returned'])
    def test_40_record_mutations_rejected(self):
        bad=v.mutations(self.records[0]);self.assertEqual(len(bad),40)
        for name,r in bad.items():
            with self.subTest(name=name),self.assertRaises((ValueError,KeyError,IndexError,TypeError)):v.check_run(r)
    def test_same_process_not_independent(self):
        require_independent(self.records)
        with self.assertRaises(ValueError):require_independent([self.records[0],self.records[0]])
    def test_consistent_nested_registers_cannot_replace_independent_field_slot_literal(self):
        for key in ('r0','r1','r2'):
            r=copy.deepcopy(self.records[0]);e=next(e for e in r['events'] if e['phase']=='nested')
            e['registers'][key]^=4;e['after_registers'][key]^=4
            with self.subTest(key=key),self.assertRaises(ValueError):v.check_run(r)
    def test_pop_return_branch_and_saved_registers_checked(self):
        for phase,key in (('pop','pc'),('pop','sp'),('pop','r4'),('pop','cpsr'),('nested_return','pc'),('nested_return','r9'),('returned','pc'),('returned','r4')):
            r=copy.deepcopy(self.records[0]);e=next(e for e in r['events'] if e['phase']==phase)
            e['after_registers'][key]^=4 if key!='cpsr' else 32
            with self.subTest(phase=phase,key=key),self.assertRaises(ValueError):v.check_run(r)
    def test_index_registers_cannot_replace_independent_queue_words(self):
        r=copy.deepcopy(self.records[0]);e=next(e for e in r['events'] if e['phase']=='load')
        e['after_registers']['r0']^=1
        with self.assertRaises(ValueError):v.check_run(r)
        r=copy.deepcopy(self.records[0]);e=next(e for e in r['events'] if e['phase']=='store')
        e['registers']['r1']^=1;e['after_registers']['r1']^=1
        raw=bytearray.fromhex(e['after_indices']);raw[4]^=1;e['after_indices']=raw.hex()
        with self.assertRaises(ValueError):v.check_run(r)
    def test_previous_failed_r18_is_not_relabelled(self):
        old=json.loads((ROOT/'analysis/fenestra-z62-business-r18/run-1.json').read_text(encoding='utf-8'))
        with self.assertRaises(ValueError):v.check_run(old)
    def test_deleted_completed_or_pending_calls_cannot_be_promoted(self):
        r=copy.deepcopy(self.records[0]);r['calls'].clear();r['summary']['pending']=[]
        with self.assertRaises(ValueError):v.check_run(r)
        r=copy.deepcopy(self.records[0]);r['events']=[e for e in r['events'] if e['phase'] not in ('nested_return','pop','returned')]
        with self.assertRaises(ValueError):v.check_run(r)

if __name__=='__main__':unittest.main()
