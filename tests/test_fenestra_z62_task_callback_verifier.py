"""Callback replay guards; these are not camera error-path tests."""
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'fenestra/z62'))
import verify_task_callback as v
from observe_task_callback import plain_step


class CallbackVerifierTests(unittest.TestCase):
    def test_missing_record_rejected(self):
        with self.assertRaises((ValueError,KeyError)):v.check_run({})

    def test_same_pid_not_independent(self):
        with self.assertRaises(ValueError):v.require_independent([{'owned_pid':7},{'owned_pid':7}])

    def test_debug_writes_and_nonisolated_steps_denied(self):
        for cmd in ('s','Hc03','P0=00','M10020000,1:00','Z0,10020000,2','c10020000'):
            with self.assertRaises(ValueError):v.allowed_command(cmd)

    def test_plain_step_uses_actual_stop_thread_not_qc(self):
        class Remote:
            def __init__(self,reply):self.reply=reply;self.commands=[]
            def select_thread(self,tid):self.commands.append(('select',tid))
            def command(self,cmd):self.commands.append(cmd);return 'QC01' if cmd=='qC' else self.reply
        r=Remote('T05thread:03;');plain_step(r,'03');self.assertEqual(r.commands,[('select',3),'vCont;s:03','qC'])
        with self.assertRaises(ValueError):plain_step(Remote('T05thread:01;'),'03')


if __name__=='__main__':unittest.main()
