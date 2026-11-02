"""Host-only reference-console staging and explicit synthetic-fixture checks."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import run_reference_console as run


class ReferenceConsoleTests(unittest.TestCase):
    def temp(self):
        return tempfile.TemporaryDirectory(dir=os.environ.get('PI_SCRATCH_DIR'))

    def test_synthetic_parameters_are_explicit_and_do_not_overwrite(self):
        with self.temp() as folder:
            destination = Path(folder) / 'candidate'
            record = run.synthetic_parameters(destination)
            self.assertTrue(record['experimental'])
            self.assertFalse(record['factory_calibration'])
            self.assertFalse(record['nor_dump'])
            for name, entry in record['groups'].items():
                data = (destination / name).read_bytes()
                self.assertEqual(len(data), entry['size'])
                self.assertEqual(data[-4:], b'ENDM')
                self.assertEqual(hashlib.sha256(data).hexdigest(), entry['sha256'])
            resource = (destination / 'group32.bin').read_bytes()
            self.assertEqual(resource[0xCE014:0xCE016], b'\x15\0')
            self.assertEqual(resource[0xBE014:0xBE016], b'\0\0')
            with self.assertRaises(FileExistsError):
                run.synthetic_parameters(destination)

    def test_fixed_reference_sources_are_clean(self):
        for profile in run.COMMITS:
            self.assertEqual(run.verify_repository(profile), ROOT / 'third_party' / f'{profile}-qemu')

    def test_z62_requires_one_explicit_parameter_source(self):
        with self.temp() as folder:
            qemu = Path(folder) / 'fake-qemu.exe'
            qemu.write_bytes(b'not executed')
            for parameters, experimental in ((None, False), (Path(folder), True)):
                with self.assertRaisesRegex(ValueError, 'exactly one'):
                    run.stage('z62', qemu, parameters, experimental)

    def test_stage_preserves_all_firmware_hashes_and_copies_tracked_source(self):
        with self.temp() as folder:
            qemu = Path(folder) / 'fake-qemu.exe'
            qemu.write_bytes(b'not executed')
            work, record = run.stage('z62', qemu, experimental_parameters=True)
            try:
                self.assertTrue((work / 'source/tools/z62_console.py').is_file())
                self.assertFalse((work / 'source/.git').exists())
                self.assertEqual(len(record['inputs']), 3)
                for name, entry in record['inputs'].items():
                    data = (work / 'inputs' / name).read_bytes()
                    self.assertEqual(len(data), entry['size'])
                    self.assertEqual(hashlib.sha256(data).hexdigest(), entry['sha256'])
                self.assertTrue(record['parameters']['experimental'])
                self.assertFalse(record['guest_patched'])
            finally:
                shutil.rmtree(work)

    def test_native_adapter_changes_only_host_paths_and_null_sink(self):
        captured = []
        class FakePopen:
            def __init__(self, command, *args, **kwargs):
                captured.append(command)
        with self.temp() as folder, patch.object(run.subprocess, 'Popen', FakePopen):
            work = Path(folder)
            original = run.install_native_process_adapter(work)
            try:
                run.subprocess.Popen(['D:\\ref\\qemu-system-arm.exe', '-M',
                                      'nikon-z62-dual-lab,master-boot-image=D:\\ref\\master.bin',
                                      '-qtest-log', '/dev/null'])
                self.assertEqual(captured[0][0], 'D:/ref/qemu-system-arm.exe')
                self.assertEqual(captured[0][2], 'nikon-z62-dual-lab,master-boot-image=D:/ref/master.bin')
                self.assertEqual(captured[0][-1], 'NUL' if os.name == 'nt' else '/dev/null')
                self.assertEqual(json.loads((work / 'effective-command-0.json').read_text()), captured[0])
            finally:
                run.subprocess.Popen = original


if __name__ == '__main__':
    unittest.main()
