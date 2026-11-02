"""Offline tests: no QEMU or camera access."""
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from z62_capture_observation import COUNTERS, PRESETS, REGIONS, preset_arguments, install_preset, observe_capture
from probe_z62_menu_timing import classify

class CaptureObservationTests(unittest.TestCase):
    def test_default_empty(self):
        self.assertEqual(preset_arguments('baseline'), [])

    def test_unknown_preset_rejected(self):
        with self.assertRaises(ValueError): preset_arguments('anything')

    def test_init_mode_does_not_enable_frame_or_pixels(self):
        args=preset_arguments('init-mode')
        self.assertEqual(len(args),4)
        self.assertFalse(any('frame-completion' in x for x in args))

    def test_popen_adapter_preserves_non_qemu_and_original_list(self):
        class Base:
            def __init__(self, command, **kwargs): self.command=command
        cls=install_preset(Base,'init-mode')
        command=['qemu-system-arm.exe','-S'];saved=list(command)
        p=cls(command)
        self.assertEqual(command,saved)
        self.assertEqual(len(p.command),6)
        self.assertEqual(cls(['python','test.py']).command,['python','test.py'])

    def test_observation_only_uses_read_commands(self):
        machine=SimpleNamespace(qmp=SimpleNamespace(command=Mock(return_value=3)),
                                _words=Mock(side_effect=lambda a,n: [0]*n))
        r=observe_capture(machine)
        self.assertEqual(r['errors'],[])
        self.assertEqual(machine.qmp.command.call_count,2*len(COUNTERS))
        self.assertTrue(all(c.args[0]=='qom-get' for c in machine.qmp.command.call_args_list))
        self.assertEqual(r['sensors']['master']['init-submissions'],3)
        self.assertEqual(machine._words.call_count,len(REGIONS))

    def test_failed_counter_is_unknown_not_zero(self):
        machine=SimpleNamespace(qmp=SimpleNamespace(command=Mock(side_effect=RuntimeError('missing'))),
                                _words=Mock(side_effect=lambda a,n:[0]*n))
        r=observe_capture(machine)
        self.assertNotIn('init-submissions',r['sensors']['master'])
        self.assertEqual(len(r['errors']),10)

    def test_missing_health_is_not_clean(self):
        r=classify([dict(stage='after-reopen',phase='running',index=1,display_enabled=True)])
        self.assertFalse(r['health_observations_complete'])
        self.assertFalse(r['no_blocking_codes_observed'])

    def test_blocking_health_is_not_clean(self):
        r=classify([dict(stage='after-reopen',phase='running',index=1,display_enabled=True,status_codes=[63],status_count=1)])
        self.assertFalse(r['no_blocking_codes_observed'])

    def test_clean_health_and_exit(self):
        r=classify([dict(stage='after-exit',phase='running',index=3,status_codes=[],status_count=0),
                    dict(stage='after-reopen',phase='running',index=1,display_enabled=True,status_codes=[],status_count=0)])
        self.assertTrue(r['no_blocking_codes_observed'])
        self.assertTrue(r['all_status_lists_empty'])
        self.assertTrue(r['left_menu_observed'])
        self.assertTrue(r['reopened_observed'])

if __name__=='__main__': unittest.main()
