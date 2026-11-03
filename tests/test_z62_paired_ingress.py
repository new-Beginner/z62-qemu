import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
import run_z62_paired_ingress as host
import z62_paired_ingress_device as device


class PairedConfigurationTests(unittest.TestCase):
    def test_default_command_preserves_parent_baseline(self):
        original = ['qemu-system-arm.exe']
        self.assertEqual(host.configure_command(original), host.parent.configure_command(original))
        self.assertEqual(original, ['qemu-system-arm.exe'])

    def test_source_requires_explicit_legacy_stop_option(self):
        with self.assertRaisesRegex(ValueError, 'explicit RAW stop'):
            host.configure_command([], paired=True)
        command = host.configure_command([], stop_control=True, paired=True)
        self.assertEqual(command.count('nikon-z72-boot-config.z62-paired-ingress=on'), 1)
        self.assertIn('nikon-z72-boot-config.z62-raw-stop-control=on', command)

    def test_duplicate_source_option_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'already supplied'):
            host.configure_command(['-global', 'nikon-z72-boot-config.z62-paired-ingress=off'],
                                   stop_control=True, paired=True)

    def test_changed_parent_input_fails_before_render(self):
        name = next(iter(device.INPUTS))
        with self.assertRaisesRegex(ValueError, 'frozen r64b'):
            device.render({name: b'changed parent input'})


if __name__ == '__main__':
    unittest.main()
