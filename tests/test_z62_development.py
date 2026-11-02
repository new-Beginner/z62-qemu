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
import types
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import reference_updates
import run_z62_development as dev
from z62_development_status import firmware_health, functional_raw_status


class DevelopmentTests(unittest.TestCase):
    def test_defaults_are_safe(self):
        args = dev.parse_args(['--experimental-parameters'])
        self.assertFalse(args.functional_raw)
        self.assertEqual(args.capture_preset, 'baseline')
        self.assertEqual(args.sd_mode, 'snapshot')
        self.assertIsNone(args.sd_card)
        self.assertEqual(args.port, 8672)
        self.assertIn(dev.VERSION, str(args.qemu))

    def test_invalid_arguments_fail(self):
        for args in ([], ['--experimental-parameters', '--port', '0'],
                     ['--experimental-parameters', '--sd-mode', 'persistent']):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                dev.parse_args(args)

    def test_raw_is_explicit_and_command_not_mutated(self):
        original = ['qemu-system-arm.exe']
        self.assertEqual(dev.configure_command(original), original)
        enabled = dev.configure_command(original, True)
        self.assertIn('nikon-z72-input-config.functional-raw=on', enabled)
        self.assertEqual(original, ['qemu-system-arm.exe'])

    def test_status_reads_only_and_rejects_incomplete(self):
        def sample(words):
            addresses = []
            def read(addr, count):
                addresses.append((addr, count))
                return words
            result = firmware_health(types.SimpleNamespace(_words=read))
            self.assertEqual(addresses, [(0xC253E0C0, 69)])
            return result
        self.assertTrue(sample([0] * 69)['firmware_status_empty'])
        words = [0x35] + [0] * 67 + [1]
        result = sample(words)
        self.assertTrue(result['firmware_health_known'])
        self.assertFalse(result['firmware_status_empty'])
        self.assertEqual(result['firmware_status_codes'], [0x35])
        for words in ([0] * 68, [0] * 68 + [69], [0] * 68 + [True],
                      [-1] + [0] * 67 + [1]):
            self.assertFalse(sample(words)['firmware_health_known'])

    def test_status_io_failure_is_unknown(self):
        def read(*args):
            raise OSError('unavailable')
        self.assertFalse(firmware_health(types.SimpleNamespace(_words=read))['firmware_health_known'])

    def test_raw_diagnostics_are_read_only_and_fail_closed(self):
        calls = []
        values = {'functional-raw': True, 'raw-accepted': 1, 'raw-rejected': 2,
                  'raw-bytes': 9142528, 'raw-last-reason': 'success'}
        def query(command, arguments):
            calls.append((command, arguments))
            return values[arguments['property']]
        machine = types.SimpleNamespace(qmp=types.SimpleNamespace(command=query))
        result = functional_raw_status(machine)['functional_raw_status']
        self.assertTrue(result['known'])
        self.assertFalse(result['live_view_verified'])
        self.assertFalse(result['packing_verified'])
        self.assertEqual(len(calls), 10)
        self.assertTrue(all(command == 'qom-get' for command, _ in calls))
        values['raw-accepted'] = True
        result = functional_raw_status(machine)['functional_raw_status']
        self.assertFalse(result['known'])
        self.assertNotIn('raw-accepted', result['engines']['master'])
        def unavailable(*args):
            raise RuntimeError('property absent in old binary')
        machine.qmp.command = unavailable
        result = functional_raw_status(machine)['functional_raw_status']
        self.assertFalse(result['known'])
        self.assertEqual(len(result['errors']), 10)

    def test_manifest_checks_binary_and_source_identity(self):
        import z62_functional_device
        with tempfile.TemporaryDirectory(dir=os.environ.get('PI_SCRATCH_DIR')) as folder:
            root = Path(folder)
            (root / 'runtime').mkdir()
            binary = root / 'runtime/qemu-system-arm.exe'
            binary.write_bytes(b'fixture-not-executable')
            self.assertIsNone(dev.verify_functional_build(binary))
            with self.assertRaises(ValueError):
                dev.verify_functional_build(binary, True)
            record = {'schema': 1, 'version': dev.VERSION,
                      'functional_device': z62_functional_device.identity(),
                      'binary_sha256': dev.digest(binary)}
            manifest = root / 'functional-build-manifest.json'
            manifest.write_text(json.dumps(record), encoding='utf-8')
            self.assertEqual(dev.verify_functional_build(binary, True), record)
            for key, bad in (('schema', 2), ('version', 'other'),
                             ('functional_device', {}), ('binary_sha256', '0' * 64)):
                manifest.write_text(json.dumps({**record, key: bad}), encoding='utf-8')
                with self.subTest(key=key), self.assertRaises(ValueError):
                    dev.verify_functional_build(binary, True)

    def test_staged_adapter_and_syntax(self):
        donor = dev.base.ROOT / 'third_party/z62-qemu'
        for persistent in (False, True):
            with self.subTest(persistent=persistent), tempfile.TemporaryDirectory(dir=os.environ.get('PI_SCRATCH_DIR')) as folder:
                root = Path(folder)
                for name in ('tools/z62_console.py', 'tools/z62_probe.py', 'tools/web_console.py', 'web-z62/console.js', 'web-z62/index.html'):
                    dst = root / name
                    dst.parent.mkdir(exist_ok=True)
                    shutil.copyfile(donor / name, dst)
                reference_updates.apply_console(root)
                dev.apply_console(root, persistent)
                code = (root / 'tools/z62_console.py').read_text(encoding='utf-8')
                self.assertIn(f"PACKAGE_VERSION = '{dev.VERSION}'", code)
                self.assertIn('state.update(firmware_health(self))', code)
                self.assertIn('snapshot=' + ('off' if persistent else 'on'), code)
                shared = (root / 'tools/web_console.py').read_text(encoding='utf-8')
                self.assertLess(shared.index('self.qmp.command("quit")'), shared.index('self.process.terminate()'))
                ast.parse(code)
                ast.parse(shared)
                node = shutil.which('node')
                self.assertIsNotNone(node, 'Node required for staged JavaScript syntax check')
                subprocess.run([node, '--check', str(root / 'web-z62/console.js')], check=True, capture_output=True)
                with self.assertRaises(ValueError):
                    dev.apply_console(root, persistent)


if __name__ == '__main__':
    unittest.main()
