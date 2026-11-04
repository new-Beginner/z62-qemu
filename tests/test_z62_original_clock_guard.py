"""Early clock qualification never replaces missing original hardware state."""
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import z62_original_clock_guard as clock


class OriginalClockGuardTests(unittest.TestCase):
    def machine(self,values,exit_code=None):
        stream=iter(values)
        return SimpleNamespace(_words=lambda address,count:next(stream),process=SimpleNamespace(poll=lambda:exit_code))

    def test_zero_frequency_waits_for_actual_readback(self):
        machine=self.machine(([0,0,0],[17,1,24_000_000]))
        with patch.object(clock.time,'sleep'):
            self.assertEqual(clock.wait_for_clock(machine),[[0,0,0],[17,1,24_000_000]])

    def test_expired_clock_is_not_replaced_with_a_default(self):
        machine=self.machine(([0,0,0],[0,0,0]))
        with patch.object(clock.time,'monotonic',side_effect=(0,.5,1.1)),patch.object(clock.time,'sleep'):
            with self.assertRaises(TimeoutError):clock.wait_for_clock(machine,1)

    def test_dead_process_cannot_become_clock_ready(self):
        with self.assertRaises(RuntimeError):clock.wait_for_clock(self.machine(([0,0,0],),exit_code=0))

    def test_unknown_or_boolean_clock_fields_rejected(self):
        for words in ([0,0],[0,0,True],[0,0,-1],[0,0,0x1_00000000]):
            with self.subTest(words=words),self.assertRaises(ValueError):clock.wait_for_clock(self.machine((words,)))


if __name__=='__main__':unittest.main()
