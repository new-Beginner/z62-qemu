"""Saved r15 replay and targeted errors; no QEMU/camera is started by these tests."""
import copy
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'fenestra/z62'))
import verify_task_launch as v


class LaunchReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = v.observer.OUTPUT
        cls.records = [json.loads((root/n).read_text()) for n in ('run-2.json','run-3-repeat.json')]

    def test_two_new_model_original_runs_replay(self):
        v.require_independent(self.records)
        self.assertEqual([v.check_run(r)['calls'] for r in self.records], [17,52])
        for r in self.records:
            self.assertFalse(r['firmware_integrated'])
            self.assertTrue(all(row['entry_before_return'] and row['return_before_entry'] for row in r['summary'].values()))

    def test_targeted_record_mutations_rejected(self):
        for name,bad in v.mutations(self.records[0]).items():
            with self.subTest(name=name), self.assertRaises((ValueError,KeyError,TypeError,IndexError)):
                v.check_run(bad)

    def test_consistent_input_register_edit_still_cannot_change_published_argument(self):
        r = copy.deepcopy(self.records[0]); e = next(e for e in r['events'] if e['phase']=='input')
        e['registers']['r1'] ^= 1; e['after_registers']['r1'] ^= 1
        r['pairs'][e['pair_index']]['input'] = copy.deepcopy(e)
        with self.assertRaisesRegex(ValueError,'Same-call input/publish'): v.check_run(r)

    def test_consistent_stack_shift_cannot_change_logged_read_addresses(self):
        r = copy.deepcopy(self.records[0]); pi = 0
        for e in r['events']:
            if e['pair_index'] != pi or e['phase']=='entered': continue
            e['registers']['sp'] += 4; e['after_registers']['sp'] += 4
            r['pairs'][pi][e['phase']] = copy.deepcopy(e)
        with self.assertRaisesRegex(ValueError,'read plan'): v.check_run(r)

    def test_process_independence_is_required(self):
        with self.assertRaises(ValueError): v.require_independent([self.records[0], self.records[0]])

    def test_memory_and_breakpoint_audit_are_not_just_counts(self):
        for change in ('memory','breakpoint'):
            r = copy.deepcopy(self.records[0])
            i = next(i for i,n in enumerate(r['rsp_commands']) if n.startswith('m' if change=='memory' else 'Z1'))
            r['rsp_commands'][i] = 'm10020000,4' if change=='memory' else 'Z1,10020000,2'
            with self.subTest(change=change), self.assertRaises(ValueError): v.check_run(r)

    def test_retained_initial_failure_is_not_promoted(self):
        r = json.loads((v.observer.OUTPUT/'run-1.json').read_text())
        self.assertIn('Unbounded original input stack', r['failure'])
        self.assertTrue(r['owned_process_closed'])
        with self.assertRaises(ValueError): v.check_run(r)


if __name__ == '__main__': unittest.main()
