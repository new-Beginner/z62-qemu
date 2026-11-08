"""Debugger control tests, no QEMU, guest state writes or firmware required."""
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, call

P=Path(__file__).resolve().parents[1]/'fenestra/z62'
sys.path.insert(0,str(P))
spec=importlib.util.spec_from_file_location('fenestra_observation',P/'observe_startup.py')
o=importlib.util.module_from_spec(spec)
spec.loader.exec_module(o)


class ObservationTests(unittest.TestCase):
    def test_stop_packet_overrides_stale_current_thread(self):
        self.assertEqual(o.stopped_thread('T05thread:03;','QC01'),'03')
        self.assertEqual(o.stopped_thread('T05watch:1000;thread:04;','QC01'),'04')
        self.assertEqual(o.stopped_thread('S05','QC02'),'02')
        with self.assertRaisesRegex(ValueError,'stopped CPU'):
            o.stopped_thread('T05','QC01')

    def test_kept_breakpoint_is_stepped_before_rearm(self):
        remote=Mock()
        remote.command.side_effect=['OK','T05thread:01;','OK']
        self.assertEqual(o.advance_breakpoint(remote,0x1002BE74,'01',True),'T05thread:01;')
        self.assertEqual(remote.mock_calls,[call.breakpoint(0x1002BE74,False),call.command('Hc01'),
            call.command('s'),call.command('Hc-1'),call.breakpoint(0x1002BE74)])

    def test_completed_breakpoint_removed_without_step(self):
        remote=Mock()
        self.assertIsNone(o.advance_breakpoint(remote,0x1002BE74,'01',False))
        self.assertEqual(remote.mock_calls,[call.breakpoint(0x1002BE74,False)])

    def test_bad_step_does_not_rearm_or_write_registers(self):
        remote=Mock()
        remote.command.side_effect=['OK','T04thread:01;']
        with self.assertRaisesRegex(ValueError,'single-step'):
            o.advance_breakpoint(remote,0x1002BE74,'01',True)
        self.assertEqual(remote.mock_calls,[call.breakpoint(0x1002BE74,False),call.command('Hc01'),call.command('s')])

    def test_bad_thread_selection_stops(self):
        remote=Mock()
        remote.command.return_value='E01'
        with self.assertRaisesRegex(ValueError,'select step'):
            o.advance_breakpoint(remote,0x1002BE74,'01',True)
        self.assertEqual(remote.mock_calls,[call.breakpoint(0x1002BE74,False),call.command('Hc01')])


if __name__=='__main__':
    unittest.main()
