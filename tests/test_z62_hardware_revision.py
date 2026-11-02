"""Runtime labels must follow a validated kernel, not just the old host layer."""
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch,Mock

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import run_z62_capture_console as host


class HardwareRevisionTests(unittest.TestCase):
    def test_base_kernel_keeps_original_revision(self):
        with patch.object(host.contacts,'verify_build',return_value={}):
            self.assertEqual(host.verified_hardware_version(Path('base.exe')),'2026.10.29-r13')

    def test_newest_descendant_requires_its_own_full_validator(self):
        validate=Mock(return_value={'version':'2026.10.30-r21'})
        with patch.object(host.contacts,'verify_build',return_value={'analog_input_device':{},'continuous_statistics_device':{}}), \
             patch('importlib.import_module',return_value=SimpleNamespace(verify_build=validate)) as imported:
            self.assertEqual(host.verified_hardware_version(Path('new.exe')),'2026.10.30-r21')
            imported.assert_called_once_with('run_z62_analog_input')
            validate.assert_called_once_with(Path('new.exe'))

    def test_unverified_descendant_does_not_receive_a_version_label(self):
        with patch.object(host.contacts,'verify_build',return_value={'analog_input_device':{}}), \
             patch('importlib.import_module',return_value=SimpleNamespace(verify_build=Mock(side_effect=ValueError('changed source')))):
            with self.assertRaisesRegex(ValueError,'changed source'):
                host.verified_hardware_version(Path('changed.exe'))


if __name__=='__main__':
    unittest.main()
