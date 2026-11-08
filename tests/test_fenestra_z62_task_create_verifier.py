"""Bounded creation replay must not accept incomplete or unsafe records."""
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'fenestra/z62'))
import verify_task_create as verifier


class TaskCreateVerifierTests(unittest.TestCase):
    def test_empty_record_rejected(self):
        with self.assertRaises((ValueError,KeyError)):verifier.check_run({})

    def test_same_pid_is_not_independent(self):
        with self.assertRaises(ValueError):verifier.require_independent([{'owned_pid':1},{'owned_pid':1}])
        verifier.require_independent([{'owned_pid':1},{'owned_pid':2}])

    def test_debugger_writes_and_traditional_step_rejected(self):
        for command in ('M10020000,1:00','P0=00','s','Hc01','c10020000','Z0,10020000,2'):
            with self.subTest(command=command),self.assertRaises(ValueError):verifier.allowed_command(command)

    def test_read_and_per_cpu_step_allowed(self):
        for command in ('m10020000,6c','Hg0','vCont;s:01','Z1,1010a268,2','g'):
            verifier.allowed_command(command)


if __name__=='__main__':unittest.main()
