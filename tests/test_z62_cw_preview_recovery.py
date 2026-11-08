"""Recovery must follow real application entry and new data, not elapsed time."""
import copy
import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from z62_cw_preview_recovery import RecoveryPlan


def sample(time,index=3,preview=10,cohort=2,publication=10):
    return {'virtual_time_ns':int(time*1e9),'application':{'index':index,'queued_keys':[],'held':[]},
        'other_pipeline_counters':{'preview-batches':preview},'firmware_status_codes':[],
        'CW_preview_source':{'cohort':cohort,'owns_source':True,'source_valid':True,
            'frames':[{'publication':publication+i,'time_ns':int((time-.2)*1e9)} for i in range(4)]}}


class RecoveryTests(unittest.TestCase):
    def enter(self):
        plan=RecoveryPlan();self.assertIsNone(plan.step(sample(8)))
        self.assertEqual(plan.step(sample(8.4))['action'],'menu');return plan

    def test_delayed_menu_never_receives_early_half_or_second_menu(self):
        plan=self.enter()
        for time in (10,14,18,25):self.assertIsNone(plan.step(sample(time)))
        self.assertEqual(len(plan.events),1)
        self.assertIsNone(plan.step(sample(26,index=1)))
        self.assertEqual(plan.step(sample(26.3,index=1))['action'],'half')

    def test_pending_key_edges_block_next_action(self):
        plan=self.enter();row=sample(10,index=1);row['application']['queued_keys']=[9]
        self.assertIsNone(plan.step(row));row['virtual_time_ns']=11_000_000_000
        self.assertIsNone(plan.step(row));self.assertEqual(len(plan.events),1)

    def test_index_only_or_old_cohort_cannot_recover(self):
        plan=self.enter();plan.step(sample(10,index=1));plan.step(sample(10.3,index=1))
        self.assertIsNone(plan.step(sample(11,preview=10,cohort=3,publication=20)))
        self.assertIsNone(plan.step(sample(11,preview=11,cohort=2,publication=20)))
        self.assertIsNone(plan.step(sample(11,preview=11,cohort=3,publication=10)))
        self.assertEqual(plan.completed,0)

    def test_four_fresh_frames_and_clean_status_required(self):
        plan=self.enter();plan.step(sample(10,index=1));plan.step(sample(10.3,index=1))
        row=sample(11,preview=11,cohort=3,publication=20);bad=copy.deepcopy(row)
        bad['CW_preview_source']['frames']*=0;self.assertIsNone(plan.step(bad))
        bad=copy.deepcopy(row);bad['firmware_status_codes']=[63];self.assertIsNone(plan.step(bad))
        bad=copy.deepcopy(row);bad['CW_preview_source']['frames'][3]=bad['CW_preview_source']['frames'][0]
        self.assertIsNone(plan.step(bad));self.assertEqual(plan.step(row)['action'],'recovered')

    def test_two_complete_cycles_are_distinct_and_terminal(self):
        plan=self.enter();plan.step(sample(10,index=1));plan.step(sample(10.3,index=1))
        self.assertEqual(plan.step(sample(11,preview=11,cohort=3,publication=20))['action'],'recovered')
        self.assertEqual(plan.step(sample(11.4,preview=12,cohort=4,publication=24))['action'],'menu')
        plan.step(sample(14,index=1,preview=12,cohort=4,publication=24))
        self.assertEqual(plan.step(sample(14.3,index=1,preview=12,cohort=4,publication=24))['action'],'half')
        self.assertEqual(plan.step(sample(15,preview=13,cohort=5,publication=30))['action'],'recovered')
        self.assertEqual(plan.phase,'complete');self.assertEqual(plan.completed,2)
        self.assertIsNone(plan.step(sample(30,preview=40,cohort=40,publication=100)))


if __name__=='__main__':unittest.main()
