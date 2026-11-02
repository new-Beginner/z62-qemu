# SPDX-License-Identifier: GPL-2.0-or-later
import ast
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import z62_capcom_device as device
import z62_capcom_status as status
import run_z62_capcom as host
import probe_z62_capcom_cycle as cycle
import build_qemu


class CapcomTests(unittest.TestCase):
    def test_native_dependency_scanner_uses_filename_and_unicode_cwd(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / '中文路径'
            root.mkdir()
            binary = root / 'qemu-system-arm.exe'
            binary.write_bytes(b'fixture')
            msys = Path(folder) / 'msys'
            libraries = msys / 'ucrt64/bin'
            libraries.mkdir(parents=True)
            (libraries / 'dep.dll').write_bytes(b'dll fixture')
            calls = []
            def inspect(command, **kw):
                calls.append((command, kw['cwd']))
                self.assertEqual(Path(command[-1]).name, command[-1])
                self.assertTrue((kw['cwd'] / command[-1]).is_file())
                return SimpleNamespace(stdout='DLL Name: dep.dll\n' if command[-1].endswith('.exe') else '')
            with patch.object(build_qemu.subprocess, 'run', side_effect=inspect):
                result = build_qemu.stage_windows(binary, msys, root / 'runtime')
            self.assertEqual(calls[0][1], root)
            self.assertIn('dep.dll', result)

    def test_adapter_consumes_exact_r5_once(self):
        base = ROOT / '.build/z62-transaction-2026.10.28-r5/source/qemu-10.2.4/hw/arm/nikon-z72.c'
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / 'source'
            arm = source / 'hw/arm'
            arm.mkdir(parents=True)
            path = arm / 'nikon-z72.c'
            path.write_bytes(base.read_bytes())
            with patch.object(device, 'WORK', root):
                device.apply_source(source)
                text = path.read_text(encoding='utf-8')
                self.assertIn('#include "nikon-z62-capcom.h"', text)
                self.assertIn('capcom_write(s, address, value);', text)
                self.assertIn('    timer_free(s->capcom_timer);', text)
                self.assertIn('    .minimum_version_id = 39,', text)
                with self.assertRaisesRegex(ValueError, 'SHA mismatch'):
                    device.apply_source(source)

    def test_disabled_command_is_unchanged_and_enabled_is_explicit(self):
        command = ['qemu-system-arm.exe', '-S']
        self.assertEqual(host.configure_command(command, False), command)
        self.assertEqual(host.configure_command(command, True)[-2:],
                         ['-global', 'nikon-z72-boot-config.z62-capcom-sync=on'])
        self.assertEqual(command, ['qemu-system-arm.exe', '-S'])

    def test_missing_diagnostics_stay_unknown(self):
        def fail(*a):
            raise OSError('disconnected')
        row = status.capcom_status(SimpleNamespace(qmp=SimpleNamespace(command=fail)))
        self.assertFalse(row['capcom_sync_status']['known'])
        self.assertEqual(row['capcom_sync_status']['engines'], {})
        self.assertTrue(row['capcom_sync_status']['errors'])

    def test_cycle_adapters_restore_on_failure(self):
        saved = (cycle.cycle.host.configure_command, cycle.cycle.timing.observe_capture, cycle.cycle.timing.stage)
        with tempfile.TemporaryDirectory() as folder:
            args = SimpleNamespace(output=Path(folder)/'new', qemu=Path('qemu.exe'), capcom_sync=True)
            with patch.object(cycle.capcom, 'verify_build', return_value={}), \
                    patch.object(cycle.cycle, 'run', side_effect=RuntimeError('fixture')):
                with self.assertRaisesRegex(RuntimeError, 'fixture'):
                    cycle.run(args)
        self.assertEqual(saved, (cycle.cycle.host.configure_command, cycle.cycle.timing.observe_capture, cycle.cycle.timing.stage))

    def test_cycle_does_not_rewrite_unowned_evidence_after_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            args = SimpleNamespace(output=Path(folder)/'new', qemu=Path('qemu.exe'), capcom_sync=True)
            original = b'{"belongs_to_another_run": true}\n'
            def raced(_):
                args.output.mkdir()
                (args.output/'report.json').write_bytes(original)
                raise FileExistsError('Another run claimed the output before stage')
            with patch.object(cycle.capcom, 'verify_build', return_value={}), \
                    patch.object(cycle.cycle, 'run', side_effect=raced):
                with self.assertRaises(FileExistsError):
                    cycle.run(args)
            self.assertEqual((args.output/'report.json').read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
