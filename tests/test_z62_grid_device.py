from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))


class GridDeviceTests(unittest.TestCase):
    def api(self):
        try:
            import z62_grid_device as device
            import run_z62_grid as host
        except ImportError as exc:
            self.fail('Independent numerical bank0 device is missing: '+str(exc))
        return device,host

    def test_enable_is_explicit_idempotent_and_preserves_original_command(self):
        _,host=self.api()
        command=['qemu-system-arm.exe','-S']
        self.assertEqual(host.configure_command(command,False),command)
        changed=host.configure_command(command,True)
        self.assertEqual(changed[-2:],['-global','nikon-z72-boot-config.z62-grid-process=on'])
        self.assertEqual(host.configure_command(changed,True),changed)
        self.assertEqual(command,['qemu-system-arm.exe','-S'])

    def test_source_drift_and_external_output_are_rejected(self):
        device,_=self.api()
        source=ROOT/'.build/z62-preview-results-format-2026.11.02-r47b/source/qemu-10.2.4/hw/arm'
        files={n:(source/n).read_bytes() for n in device.INPUTS}
        files['nikon-z72-input-config.c']+=b'\n'
        with self.assertRaises(ValueError): device.render(files)
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError): device.apply_source(Path(folder))
            self.assertEqual(list(Path(folder).iterdir()),[])
