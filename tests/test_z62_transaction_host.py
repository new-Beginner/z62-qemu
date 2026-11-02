# SPDX-License-Identifier: GPL-2.0-or-later
import ast
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import reference_updates
import run_z62_transaction as host
import probe_z62_transaction_cycle as probe
import z62_transaction_status as status


class TransactionHostTests(unittest.TestCase):
    def temporary(self):
        return tempfile.TemporaryDirectory(dir=os.environ.get('PI_SCRATCH_DIR'))

    def test_defaults_and_explicit_dependencies(self):
        args = host.parse_args(['--experimental-parameters'])
        self.assertFalse(args.raw_completion)
        self.assertFalse(args.functional_raw)
        self.assertEqual(args.capture_preset, 'baseline')
        self.assertEqual(args.sd_mode, 'snapshot')
        self.assertEqual(args.port, 8673)
        for extra in (['--raw-completion'], ['--port', '0'], ['--sd-mode', 'persistent']):
            with self.subTest(extra=extra), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                host.parse_args(['--experimental-parameters'] + extra)
        for extra in (['--raw-completion'], ['--cycles', '0']):
            with self.subTest(extra=extra), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                probe.parse_args(['--output', 'unused'] + extra)

    def test_commands_not_mutated_and_never_inject_guest_events(self):
        command = ['qemu-system-arm.exe', '-S']
        self.assertEqual(host.configure_command(command), command)
        self.assertEqual(len(host.configure_command(command, True)), len(command) + 2)
        both = host.configure_command(command, True, True)
        self.assertEqual(both[-4:], ['-global', 'nikon-z72-input-config.functional-raw=on',
                                    '-global', 'nikon-z62-sensor-config.functional-raw-completion=on'])
        self.assertEqual(command, ['qemu-system-arm.exe', '-S'])
        with self.assertRaises(ValueError):
            host.configure_command(command, False, True)

    def test_status_read_only_and_malformed_is_unknown(self):
        calls = []
        values = {name: (True if name == status.PROPERTIES[0] else 0) for name in status.PROPERTIES}
        def query(cmd, args):
            calls.append((cmd, args))
            return values[args['property']]
        values['raw-completion-last-reason'] = 'reset'
        machine = SimpleNamespace(qmp=SimpleNamespace(command=query))
        row = status.transaction_status(machine)['transaction_bridge']
        self.assertTrue(row['known'])
        self.assertFalse(row['hardware_timing_verified'])
        self.assertEqual(len(calls), len(status.PROPERTIES) * 2)
        self.assertTrue(all(c[0] == 'qom-get' for c in calls))
        values[status.PROPERTIES[1]] = True
        row = status.transaction_status(machine)['transaction_bridge']
        self.assertFalse(row['known'])
        self.assertNotIn(status.PROPERTIES[1], row['engines']['master'])
        def fail(*a):
            raise OSError('disconnected')
        machine.qmp.command = fail
        row = status.transaction_status(machine)['transaction_bridge']
        self.assertFalse(row['known'])
        self.assertEqual(row['engines'], {'master': {}, 'slave': {}})

    def test_staged_adapter_syntax_and_version(self):
        for persistent in (False, True):
            with self.subTest(persistent=persistent), self.temporary() as folder:
                root = Path(folder)
                for name in ('tools/z62_console.py', 'tools/z62_probe.py', 'tools/web_console.py',
                             'web-z62/index.html', 'web-z62/console.js'):
                    dest = root / name
                    dest.parent.mkdir(exist_ok=True)
                    shutil.copyfile(ROOT / 'third_party/z62-qemu' / name, dest)
                reference_updates.apply_console(root)
                host.apply_console(root, persistent)
                text = (root / 'tools/z62_console.py').read_text(encoding='utf-8')
                ast.parse(text)
                ast.parse((root / 'tools/web_console.py').read_text(encoding='utf-8'))
                self.assertIn(f"PACKAGE_VERSION = '{host.VERSION}'", text)
                self.assertIn('state.update(transaction_status(self))', text)
                self.assertIn('snapshot=' + ('off' if persistent else 'on'), text)
                html = (root / 'web-z62/index.html').read_text(encoding='utf-8')
                self.assertNotIn(host.r4.VERSION, html)
                self.assertIn(host.VERSION, html)
                subprocess.run(['node', '--check', str(root / 'web-z62/console.js')], check=True, capture_output=True)
                with self.assertRaises(ValueError):
                    host.apply_console(root, persistent)

    def test_manifest_requires_both_device_identities(self):
        identity = {'fixture': 'r5'}
        fake_module = SimpleNamespace(identity=lambda: identity)
        with self.temporary() as folder, patch.dict(sys.modules, {'z62_transaction_device': fake_module}):
            root = Path(folder)
            (root / 'runtime').mkdir()
            binary = root / 'runtime/qemu-system-arm.exe'
            binary.write_bytes(b'test fixture not executable')
            record = dict(schema=1, version=host.VERSION, transaction_device=identity,
                          binary_sha256=host.digest(binary))
            manifest = root / 'transaction-build-manifest.json'
            manifest.write_text(json.dumps(record))
            with patch.object(host.r4, 'verify_functional_build', return_value={'binary_sha256':record['binary_sha256']}) as raw:
                self.assertEqual(host.verify_build(binary), record)
                raw.assert_called_once_with(binary, True)
                for key, value in [('schema', 2), ('version', 'r4'), ('transaction_device', {}), ('binary_sha256', '')]:
                    manifest.write_text(json.dumps({**record, key:value}))
                    with self.subTest(key=key), self.assertRaises(ValueError):
                        host.verify_build(binary)
                manifest.write_text(json.dumps(record))
                raw.return_value = {'binary_sha256':'mismatch'}
                with self.assertRaises(ValueError):
                    host.verify_build(binary)

    def test_existing_evidence_is_untouched(self):
        with self.temporary() as folder:
            root = Path(folder)
            path = root / 'report.json'
            original = b'{"historic": true}\n'
            path.write_bytes(original)
            args = probe.parse_args(['--output', str(root)])
            with patch.object(probe.host, 'verify_build', return_value={}), self.assertRaises(FileExistsError):
                probe.run(args)
            self.assertEqual(path.read_bytes(), original)

    def test_probe_adapters_restore_after_failure(self):
        with self.temporary() as folder:
            output = Path(folder) / 'new'
            args = probe.parse_args(['--output', str(output), '--functional-raw', '--raw-completion'])
            originals = (probe.timing.stage, probe.timing.install_native_process_adapter,
                         probe.timing.observe_capture, subprocess.Popen, list(sys.path))
            def fail(legacy):
                self.assertFalse(legacy.functional_raw)
                self.assertFalse(legacy.development_host)
                sys.path.insert(0, 'fixture-added-path')
                raise RuntimeError('expected injected failure')
            with patch.object(probe.host, 'verify_build', return_value={}), patch.object(probe.timing, 'run', side_effect=fail):
                with self.assertRaisesRegex(RuntimeError, 'expected injected failure'):
                    probe.run(args)
            self.assertEqual(originals, (probe.timing.stage, probe.timing.install_native_process_adapter,
                                       probe.timing.observe_capture, subprocess.Popen, list(sys.path)))
            self.assertTrue(args.functional_raw)

    def test_probe_composition_and_metadata_preserve_failed_verdict(self):
        with self.temporary() as folder:
            root = Path(folder)
            output = root / 'new'
            args = probe.parse_args(['--output', str(output), '--functional-raw', '--raw-completion'])
            commands = []
            original_popen = subprocess.Popen
            class Recorder:
                def __init__(self, command, *a, **kw):
                    commands.append(command)
            def install(work):
                subprocess.Popen = Recorder
                return original_popen
            def query(command, arguments):
                self.assertEqual(command, 'qom-get')
                name = arguments['property']
                if 'reason' in name:
                    return 'fixture'
                return True if name in ('functional-raw', 'functional-raw-completion') else 2
            machine = SimpleNamespace(qmp=SimpleNamespace(command=query))
            def legacy(legacy_args):
                output.mkdir()
                _, identity = probe.timing.stage('z62', args.qemu)
                identity['functional_raw'] = False  # legacy metadata must be corrected
                (output / 'session.json').write_text(json.dumps(identity))
                probe.timing.install_native_process_adapter(root)
                subprocess.Popen(['qemu-system-arm.exe', '-S'])
                observations = probe.timing.observe_capture(machine)
                self.assertTrue(observations['transaction_bridge']['known'])
                self.assertTrue(observations['functional_raw_status']['known'])
                return {'menu_cycle_state_passed': False, 'samples': [], 'capture': observations}
            with patch.object(probe.host, 'verify_build', return_value={'test': 1}), \
                 patch.object(probe.host, 'apply_console'), \
                 patch.object(probe.timing, 'stage', return_value=(root, {})), \
                 patch.object(probe.timing, 'install_native_process_adapter', side_effect=install), \
                 patch.object(probe.timing, 'observe_capture', return_value={}), \
                 patch.object(probe.timing, 'run', side_effect=legacy):
                result = probe.run(args)
            self.assertFalse(result['menu_cycle_state_passed'])
            self.assertEqual(commands, [host.configure_command(['qemu-system-arm.exe', '-S'], True, True)])
            for name in ('session.json', 'report.json'):
                saved = json.loads((output / name).read_text())
                self.assertTrue(saved['functional_raw'])
                self.assertTrue(saved['raw_completion'])
            self.assertIs(subprocess.Popen, original_popen)


if __name__ == '__main__':
    unittest.main()
