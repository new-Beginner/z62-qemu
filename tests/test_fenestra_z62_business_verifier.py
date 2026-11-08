"""r18 preserved real bounded failures: valid prefixes must never become full passes."""
import copy
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'fenestra/z62'))
import business_contract as t
import verify_business as full
import verify_business_prefix as v
from startup_contract import ROOT
from verify_task_create import require_independent

class BusinessVerifierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records=[json.loads((ROOT/'analysis/fenestra-z62-business-r18'/n).read_text(encoding='utf-8'))
            for n in ('run-1.json','run-2-repeat.json')]
    def test_real_prefixes_only_not_full_acceptance(self):
        stats=[v.check_prefix(r) for r in self.records]
        self.assertEqual([s['returned'] for s in stats],[42,44])
        self.assertEqual([len(s['pending_calls']) for s in stats],[4,4])
        self.assertEqual([s['returned_signature_kinds'] for s in stats],[[1],[1]])
        for s,r in zip(stats,self.records):
            self.assertFalse(s['full_run_passed']);self.assertFalse(s['accepted_run'])
            self.assertFalse(s['bounded_registered_business_return_verified'])
            self.assertEqual({c['role'] for c in s['returned_chains']},{'master','slave'})
            self.assertTrue(all(c['registration_index'] is not None for c in s['returned_chains']))
            with self.assertRaises(ValueError):full.check_run(r)
    def test_39_record_errors_rejected(self):
        bad=v.mutations(self.records[0]);self.assertEqual(len(bad),39)
        for name,r in bad.items():
            with self.subTest(name=name),self.assertRaises((ValueError,KeyError,IndexError,TypeError)):v.check_prefix(r)
    def test_same_process_not_independent(self):
        require_independent(self.records)
        with self.assertRaises(ValueError):require_independent([self.records[0],self.records[0]])
    def test_consistent_blx_argument_mutation_does_not_replace_slot(self):
        r=copy.deepcopy(self.records[0]);c=r['contract'];rows=[];calls=[]
        for e in r['events']:
            if e['phase']=='call':
                e['registers']['r0']^=1;e['after_registers']['r0']^=1
                with self.assertRaisesRegex(ValueError,'signature/arguments'):t.ingest(rows,calls,e,c['roles'][e['role']])
                break
            t.ingest(rows,calls,e,c['roles'][e['role']])
        else:self.fail('No real call')
    def test_consistent_store_mutation_does_not_replace_entry_input(self):
        r=copy.deepcopy(self.records[0]);c=r['contract'];rows=[];calls=[]
        for e in r['events']:
            if e['phase']=='store':
                e['registers']['r6']^=1;e['after_registers']['r6']^=1
                raw=bytearray.fromhex(e['after_object']);raw[36]^=1;e['after_object']=raw.hex()
                with self.assertRaisesRegex(ValueError,'Setter source'):t.ingest(rows,calls,e,c['roles'][e['role']])
                break
            t.ingest(rows,calls,e,c['roles'][e['role']])
        else:self.fail('No real STRD')
    def test_unreturned_calls_cannot_be_omitted_from_stream(self):
        r=copy.deepcopy(self.records[0]);i=next(s['sequence'] for s in r['calls'] if s['returned'] is None)
        r['events'].pop(i)
        with self.assertRaises(ValueError):v.check_prefix(r)
    def test_old_r17_record_not_business_evidence(self):
        r=json.loads((ROOT/'analysis/fenestra-z62-task-chain-r17/run-1.json').read_text())
        with self.assertRaises(ValueError):v.check_prefix(r)

if __name__=='__main__':unittest.main()
