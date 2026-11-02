"""Opt-in reference updates; no firmware execution in these unit tests."""
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import build_reference_qemu as build
import reference_updates as update
import run_reference_console as console
import test_reference_build as fixtures
import z62_reference_features as features


class ReferenceUpdatesTests(unittest.TestCase):
    def temp(self):
        return tempfile.TemporaryDirectory(dir=os.environ.get('PI_SCRATCH_DIR'))

    def test_upstream_sources_are_pinned_and_verified(self):
        self.assertEqual({name: update.sha(data) for name, data in update.upstream_files().items()}, update.FILES)
        self.assertEqual(update.identity()['version'], features.VERSION)

    def test_prepared_source_only_changes_declared_devices_and_diagnostics(self):
        with self.temp() as folder:
            work = Path(folder)
            repo = build.verify_repository('z62')
            build.snapshot_donor(repo, work / 'donor')
            source = fixtures.ReferenceBuildTests().scaffold(work / 'source')
            build.prepare_source(source, work / 'donor')
            before = build.tree_hashes(source)
            original = (source / 'hw/arm/nikon-z72.c').read_text(encoding='utf-8')
            update.apply_source(source)
            after = build.tree_hashes(source)
            changed = {name for name in before.keys() | after.keys() if before.get(name) != after.get(name)}
            self.assertEqual(changed, {'hw/arm/nikon-z72.c', 'hw/arm/meson.build',
                                      'hw/arm/nikon-z72-controller-i2c.c',
                                      'hw/arm/nikon-z72-controller-panel.c',
                                      'hw/arm/nikon-z62-input-trace.h'})
            text = (source / 'hw/arm/nikon-z72.c').read_text(encoding='utf-8')
            start, end = 'static void frame_sync_tick', 'static bool boot_config_sd_inserted'
            self.assertEqual(text.split(start)[1].split(end)[0], original.split(start)[1].split(end)[0])
            self.assertIn('.minimum_version_id = 38', text)
            self.assertIn('s->input_trace_count = 0;', text)
            with self.assertRaises(ValueError):
                update.apply_source(source)
            self.assertEqual(after, build.tree_hashes(source))

    def test_console_staging_is_host_only_and_compiles(self):
        with self.temp() as folder:
            source = Path(folder) / 'source'
            console.copy_tracked_source(console.verify_repository('z62'), source)
            before = build.tree_hashes(source)
            update.apply_console(source)
            after = build.tree_hashes(source)
            changed = {name for name in before.keys() | after.keys() if before.get(name) != after.get(name)}
            self.assertEqual(changed, {'tools/z62_console.py', 'tools/z62_probe.py', 'tools/z62_reference_features.py'})
            for name in changed:
                compile((source / name).read_bytes(), name, 'exec')
            text = (source / 'tools/z62_console.py').read_text(encoding='utf-8')
            self.assertIn('state.update(diagnostics(self))', text)
            self.assertIn(update.VERSION, text)
            with self.assertRaises(ValueError):
                update.apply_console(source)
            self.assertEqual(after, build.tree_hashes(source))

    def test_switches_are_off_by_default_and_do_not_modify_command(self):
        command = ['qemu', '-M', 'nikon-z62-dual-lab']
        args = SimpleNamespace(sampling_source=False, input_trace=False)
        self.assertEqual(features.configure_command(command, args), command)
        args.sampling_source = args.input_trace = True
        enabled = features.configure_command(command, args)
        self.assertIn('nikon-z72-boot-config.sensor-sample=on', enabled)
        self.assertIn('nikon-z72-boot-config.sample-counter=on', enabled)
        self.assertIn('nikon-z72-boot-config.input-trace=on', enabled)
        self.assertEqual(len(command), 3)

    def test_updated_binary_identity_and_hash_are_required(self):
        with self.temp() as folder:
            work = Path(folder)
            binary = work / 'runtime/qemu-system-arm.exe'
            binary.parent.mkdir()
            binary.write_bytes(b'fake, never executed')
            manifest = work / 'reference-build-manifest.json'
            data = {'reference_updates': update.identity(), 'profile': 'z62',
                    'binary_sha256': update.sha(binary.read_bytes())}
            manifest.write_text(json.dumps(data))
            update.verify_binary(binary)
            binary.write_bytes(b'modified')
            with self.assertRaisesRegex(ValueError, 'does not match'):
                update.verify_binary(binary)
            data['binary_sha256'] = update.sha(binary.read_bytes())
            data['reference_updates']['version'] = 'old'
            manifest.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                update.verify_binary(binary)

    def test_diagnostics_are_read_only_and_discover_paths(self):
        machine = SimpleNamespace(args=SimpleNamespace(sampling_source=True, input_trace=True), qmp=Mock())
        def reply(command, args):
            if command == 'qom-list':
                return [{'name': f'device[{n}]', 'type': 'child<nikon-z72-boot-config>'} for n in (3, 8)]
            self.assertEqual(command, 'qom-get')
            return '' if args['property'].endswith(('log', 'image')) else 0
        machine.qmp.command.side_effect = reply
        result = features.diagnostics(machine)
        self.assertFalse(result['sensor_pixels_modeled'])
        self.assertFalse(result['shoulder_physical_segments'])
        self.assertEqual(len(result['input_trace']), 2)
        self.assertTrue(all(call.args[0] in ('qom-get', 'qom-list') for call in machine.qmp.command.call_args_list))

    def test_updates_are_z62_only_and_default_builder_unchanged(self):
        args = build.parse_args(['z62', '--msys2-dir', 'unused'])
        self.assertFalse(args.z62_updates)
        self.assertNotIn('reference_updates', build.identity('z62'))
        self.assertIn('reference_updates', build.identity('z62', True))
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            build.parse_args(['z72', '--msys2-dir', 'unused', '--z62-updates'])


if __name__ == '__main__':
    unittest.main()
