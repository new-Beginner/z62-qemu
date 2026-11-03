from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import z62_photo_results_device as device
import run_z62_photo_results as host


class PhotoResultsSource(unittest.TestCase):
    def test_new_layout_has_its_own_default_off_property(self):
        root=device.ROOT/'.build/z62-grid-geometry-2026.11.03-r52/source/qemu-10.2.4/hw/arm'
        inputs={name:(root/name).read_bytes() for name in device.INPUTS}
        original=dict(inputs)
        output=device.render(inputs)
        self.assertEqual(inputs,original)
        board=output['nikon-z72.c'].decode()
        self.assertIn('z62_photo_result_layouts, false)',board)
        self.assertIn('.minimum_version_id = 48',board)
        self.assertIn('grid_completed_rows != 34',board)
        self.assertIn('s->z62_photo_result_layouts && height == 40',output['nikon-z62-grid.h'].decode())
        self.assertEqual(output[device.HEADER.name],device.HEADER.read_bytes())

    def test_unsupported_parent_refused(self):
        with self.assertRaises(ValueError):
            device.render({name:b'invalid' for name in device.INPUTS})

    def test_option_is_explicit_and_idempotent(self):
        command=host.configure_command(['qemu'],True,True,False)
        self.assertNotIn('nikon-z72-boot-config.z62-photo-result-layouts=on',command)
        enabled=host.configure_command(command,True,True,True)
        self.assertIn('nikon-z72-boot-config.z62-photo-result-layouts=on',enabled)
        self.assertEqual(enabled,host.configure_command(enabled,True,True,True))


if __name__=='__main__':
    unittest.main()
