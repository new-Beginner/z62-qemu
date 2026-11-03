from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import z62_grid_geometry_device as device
import run_z62_grid_geometry as host


class GridGeometrySource(unittest.TestCase):
    def test_rendered_source_isolated_and_default_off(self):
        root = device.ROOT/'.build/z62-grid-2026.11.02-r48/source/qemu-10.2.4/hw/arm'
        inputs = {name:(root/name).read_bytes() for name in device.INPUTS}
        unchanged = dict(inputs)
        result = device.render(inputs)
        self.assertEqual(inputs,unchanged)
        board = result['nikon-z72.c'].decode()
        self.assertIn('z62_grid_geometry, false)',board)
        self.assertIn('z62_grid_retained_input, false)',board)
        self.assertIn('.minimum_version_id = 47',board)
        self.assertIn('grid_consumed_request > s->grid_request_seq',board)
        self.assertEqual(result[device.PIXELS.name],device.PIXELS.read_bytes())

    def test_modified_parent_refused(self):
        with self.assertRaises(ValueError):
            device.render({name:b'not frozen r48' for name in device.INPUTS})

    def test_geometry_and_retained_inputs_are_independent_opt_ins(self):
        off = host.configure_command(['qemu'],False,False)
        geometry = host.configure_command(['qemu'],True,False)
        both = host.configure_command(['qemu'],True,True)
        self.assertNotIn('nikon-z72-boot-config.z62-grid-geometry=on',off)
        self.assertIn('nikon-z72-boot-config.z62-grid-geometry=on',geometry)
        self.assertNotIn('nikon-z72-boot-config.z62-grid-retained-input=on',geometry)
        self.assertIn('nikon-z72-boot-config.z62-grid-retained-input=on',both)
        self.assertEqual(host.configure_command(both,True,True),both)


if __name__ == '__main__':
    unittest.main()
