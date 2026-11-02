"""Pinned reference firmware extraction, no camera or firmware patching."""
from contextlib import redirect_stdout
import hashlib
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import prepare_reference_firmware as reference


class ReferenceFirmwareTests(unittest.TestCase):
    def temp(self):
        return tempfile.TemporaryDirectory(dir=os.environ.get('PI_SCRATCH_DIR'))

    def test_both_original_containers_have_exact_complete_members(self):
        for profile, spec in reference.PROFILES.items():
            with self.subTest(profile=profile), self.temp() as folder, redirect_stdout(io.StringIO()):
                destination = Path(folder) / 'members'
                manifest = reference.prepare(profile, destination=destination)
                self.assertEqual(reference.prepare(profile, destination=destination), manifest)
                self.assertEqual(len(manifest['modules']), 3)
                self.assertFalse(manifest['integrity']['header_signature_verified'])
                self.assertFalse(manifest['nor_or_factory_parameters_included'])
                for filename, size, digest in spec['members'].values():
                    data = (destination / filename).read_bytes()
                    self.assertEqual(len(data), size)
                    self.assertEqual(hashlib.sha256(data).hexdigest(), digest)
                    self.assertEqual(reference.binascii.crc_hqx(data, 0), 0)

    def test_changed_output_is_not_overwritten_or_partially_completed(self):
        with self.temp() as folder:
            destination = Path(folder)
            changed = destination / 'slave.bin'
            changed.write_bytes(b'preserve user bytes')
            with self.assertRaisesRegex(ValueError, 'Refusing changed output'):
                reference.prepare('z72', destination=destination)
            self.assertEqual(changed.read_bytes(), b'preserve user bytes')
            self.assertFalse((destination / 'master.bin').exists())
            self.assertFalse((destination / 'manifest.json').exists())

    def test_wrong_original_identity_is_refused_before_outputs(self):
        with self.temp() as folder:
            path = Path(folder) / 'wrong.bin'
            path.write_bytes(b'not a Nikon update')
            destination = Path(folder) / 'outputs'
            with self.assertRaisesRegex(ValueError, 'Wrong original firmware identity'):
                reference.prepare('z72', input_path=path, destination=destination)
            self.assertFalse(destination.exists())

    def test_output_cannot_contain_original_input(self):
        with self.temp() as folder:
            path = Path(folder) / 'original.bin'
            path.write_bytes(b'original untouched')
            with self.assertRaisesRegex(ValueError, 'must not contain'):
                reference.prepare('z72', input_path=path, destination=Path(folder))
            self.assertEqual(path.read_bytes(), b'original untouched')

    def test_cross_model_package_is_rejected(self):
        with self.temp() as folder:
            path = ROOT / reference.PROFILES['z62']['input']
            with self.assertRaisesRegex(ValueError, 'Wrong original firmware identity'):
                reference.prepare('z72', input_path=path, destination=Path(folder))
            self.assertEqual(list(Path(folder).iterdir()), [])


if __name__ == '__main__':
    unittest.main()
