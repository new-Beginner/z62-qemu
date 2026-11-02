from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))


class PreviewResultsTests(unittest.TestCase):
    def api(self):
        try:
            import z62_preview_results_device as device
            import run_z62_preview_results as host
        except ImportError as exc:
            self.fail('Independent preview result device is missing: ' + str(exc))
        return device, host

    def test_opt_in_is_idempotent_and_does_not_modify_callers_command(self):
        _, host = self.api()
        original = ['qemu-system-arm.exe', '-S']
        self.assertEqual(host.configure_command(original, False), original)
        enabled = host.configure_command(original, True)
        self.assertEqual(enabled[-2:], ['-global', 'nikon-z72-boot-config.z62-preview-results=on'])
        self.assertEqual(host.configure_command(enabled, True), enabled)
        self.assertEqual(original, ['qemu-system-arm.exe', '-S'])

    def test_changed_parent_and_unowned_workspace_are_rejected(self):
        device, _ = self.api()
        parent = ROOT/'.build/z62-scene-file-2026.11.01-r24/source/qemu-10.2.4/hw/arm'
        data = {n: (parent/n).read_bytes() for n in device.INPUTS}
        data['nikon-z72.c'] += b'\n'
        with self.assertRaises(ValueError):
            device.render(data)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                device.apply_source(Path(directory))
            self.assertEqual(list(Path(directory).iterdir()), [])
