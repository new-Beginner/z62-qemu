# SPDX-License-Identifier: GPL-2.0-or-later
from pathlib import Path, PureWindowsPath
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
import z62_raw_stream_device as device
from build_z62_raw_stream import copy_verified_source, comparison_path


class RawStreamSourceTests(unittest.TestCase):
    def test_extended_windows_paths_keep_containment_and_reject_escape(self):
        root = PureWindowsPath('D:/workspace/source')
        normal = PureWindowsPath('D:/workspace/source/accel/accel-irq.c')
        extended = PureWindowsPath('\\\\?\\D:\\workspace\\source\\accel\\accel-irq.c')
        self.assertFalse(extended.is_relative_to(root))
        self.assertEqual(comparison_path(extended), normal)
        self.assertTrue(comparison_path(extended).is_relative_to(root))
        self.assertFalse(comparison_path(PureWindowsPath('\\\\?\\D:\\outside\\x')).is_relative_to(root))
        unc = PureWindowsPath('\\\\?\\UNC\\server\\share\\source\\x')
        self.assertTrue(comparison_path(unc).is_relative_to(PureWindowsPath('\\\\server\\share\\source')))
        device_path = PureWindowsPath('\\\\?\\GLOBALROOT\\Device\\HarddiskVolume1')
        self.assertEqual(comparison_path(device_path), device_path)

    def test_source_is_fixed_r6_and_preserves_legacy_completion(self):
        source = ROOT/'.build/z62-capcom-2026.10.28-r6/source/qemu-10.2.4/hw/arm/nikon-z72.c'
        output = device.render(source.read_bytes())
        self.assertIn('raw_stream_control(s, address, value);', output)
        self.assertIn('qdev_get_gpio_in_named(config, "raw-stream-dma-done", 0)', output)
        self.assertIn('qdev_connect_gpio_out_named(config, "raw-sensor-complete", 0,', output)
        self.assertIn('.minimum_version_id = 40,', output)
        with self.assertRaisesRegex(ValueError, 'SHA mismatch'):
            device.render(output.encode('utf-8'))

    def test_parallel_source_copy_is_hash_bound_and_never_overwrites(self):
        import hashlib
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            original, destination = root/'old', root/'new'
            original.mkdir()
            (original/'input.c').write_bytes(b'known source')
            hashes = {'input.c': hashlib.sha256(b'known source').hexdigest()}
            copy_verified_source(original, destination, hashes, workers=2)
            self.assertEqual((destination/'input.c').read_bytes(), b'known source')
            with self.assertRaises(FileExistsError):
                copy_verified_source(original, destination, hashes, workers=2)
            (original/'input.c').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'hash changed'):
                copy_verified_source(original, root/'third', hashes, workers=2)

    def test_nested_parallel_copy_can_resume_only_identical_files(self):
        import hashlib
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)/'中文工作区'
            original, destination = root/'old', root/'new'
            hashes = {}
            for index in range(40):
                name = f'group-{index%7}/nested-{index}/input.c'
                path = original/name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(str(index).encode())
                hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
            copy_verified_source(original, destination, hashes, workers=6)
            copy_verified_source(original, destination, hashes, workers=6, resume=True)
            target = destination/next(iter(hashes))
            target.write_bytes(b'preserve user modification')
            with self.assertRaisesRegex(ValueError, 'partial source differs'):
                copy_verified_source(original, destination, hashes, workers=6, resume=True)
            self.assertEqual(target.read_bytes(), b'preserve user modification')


if __name__ == '__main__':
    unittest.main()
