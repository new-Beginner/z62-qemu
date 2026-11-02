"""Regression tests for timing acceptance and cleanup; no VM/hardware."""
import contextlib
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from probe_z62_menu_timing import navigation_passed, close_and_restore, classify

class TimingReviewTests(unittest.TestCase):
    def state(self):
        return dict(phase='running',index=1,display_enabled=True,queued=[],status_codes=[],status_count=0)

    def test_navigation_requires_menu_not_just_pixels(self):
        row=self.state();self.assertTrue(navigation_passed(row,True))
        for change in ({'index':3},{'display_enabled':False},{'phase':'failed'},
                       {'queued':[4]},{'status_codes':None},{'status_codes':[63]},
                       {'observation_error':'unreadable'}):
            with self.subTest(change=change):
                self.assertFalse(navigation_passed(dict(row,**change),True))
        self.assertFalse(navigation_passed(row,False))

    def test_unknown_status_is_not_healthy_or_proven_blocking(self):
        row = dict(self.state(), stage='after-reopen', status_codes=[0x35], status_count=1)
        self.assertFalse(navigation_passed(row, True))
        verdict = classify([row])
        self.assertTrue(verdict['health_observations_complete'])
        self.assertTrue(verdict['no_blocking_codes_observed'])
        self.assertFalse(verdict['all_status_lists_empty'])

    def test_malformed_health_fails_closed_without_crashing(self):
        row = dict(self.state(), stage='after-reopen')
        for change in ({'status_count': None}, {'status_count': False},
                       {'status_count': -1}, {'status_count': 69},
                       {'status_count': 1}, {'status_codes': [False], 'status_count': 1},
                       {'status_codes': ['53'], 'status_count': 1},
                       {'status_codes': [None], 'status_count': 1},
                       {'status_codes': [-1], 'status_count': 1},
                       {'status_codes': [0x100000000], 'status_count': 1},
                       {'status_codes': 'unreadable'}, {'status_codes': None}):
            with self.subTest(change=change):
                sample = dict(row, **change)
                self.assertFalse(navigation_passed(sample, True))
                verdict = classify([sample])
                self.assertFalse(verdict['health_observations_complete'])
                self.assertFalse(verdict['all_status_lists_empty'])
                self.assertFalse(verdict['no_blocking_codes_observed'])
        for key in ('status_count', 'status_codes'):
            sample = {k: v for k, v in row.items() if k != key}
            self.assertFalse(navigation_passed(sample, True))
            self.assertFalse(classify([sample])['health_observations_complete'])

    def test_empty_complete_health_passes_but_earlier_status_is_not_erased(self):
        row = dict(self.state(), stage='after-reopen')
        self.assertTrue(classify([row])['all_status_lists_empty'])
        earlier = dict(row, stage='after-exit', status_codes=[0x35], status_count=1)
        self.assertFalse(classify([earlier, row])['all_status_lists_empty'])
        self.assertFalse(classify([])['all_status_lists_empty'])

    def test_cleanup_failure_restores_popen_and_preserves_primary_error(self):
        original=subprocess.Popen
        machine=SimpleNamespace(process=SimpleNamespace(poll=Mock(return_value=None)),
                                close=Mock(side_effect=TimeoutError('close timed out')))
        record={'menu_cycle_state_passed':True,'failure':{'type':'ValueError'}}
        with patch.object(subprocess,'Popen',object()):
            close_and_restore(machine,original,record)
            self.assertIs(subprocess.Popen,original)
        self.assertEqual(record['failure'],{'type':'ValueError'})
        self.assertEqual(record['cleanup_error']['type'],'TimeoutError')
        self.assertFalse(record['process_closed'])
        self.assertFalse(record['menu_cycle_state_passed'])

    def test_successful_cleanup_checks_captured_process(self):
        process=SimpleNamespace(poll=Mock(return_value=0))
        machine=SimpleNamespace(process=process,close=Mock())
        record={}
        close_and_restore(machine,subprocess.Popen,record)
        self.assertTrue(record['process_closed'])
        process.poll.assert_called_once()

if __name__=='__main__':unittest.main()
