"""Host-only reference builder tests: no compilation, downloads or guest runs."""
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import build_reference_qemu as build

SCREEN_OLD = '''    linebuf = qemu_pixman_linebuf_create(PIXMAN_BE_r8g8b8, width);
    for (y = 0; y < height; y++) {
        qemu_pixman_linebuf_fill(linebuf, image, width, 0, y);
        if (qio_channel_write_all(QIO_CHANNEL(ioc),
                                  (char *)pixman_image_get_data(linebuf),
                                  pixman_image_get_stride(linebuf), errp) < 0) {
            return false;
        }
    }

    return true;'''
DEVICE_DEFINES = ''.join('#define ' + name + ' 1\n' for name in
                         ('CONFIG_SD', 'CONFIG_SDHCI', 'CONFIG_NIKON_Z72_LAB'))


class ReferenceBuildTests(unittest.TestCase):
    def temp(self):
        return tempfile.TemporaryDirectory(dir=os.environ.get('PI_SCRATCH_DIR'))

    def scaffold(self, source):
        files = {'VERSION': '10.2.4\n', 'hw/arm/meson.build': '', 'hw/arm/Kconfig': '',
                 'configs/devices/arm-softmmu/default.mak': '',
                 'hw/sd/Kconfig': 'config SDHCI\n    bool\n    select SD\n',
                 'ui/ui-qmp-cmds.c': SCREEN_OLD,
                 '.z6ii-verified-extraction': build.upstream.ARCHIVE_SHA256 + '\n'}
        for name, text in files.items():
            path = source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding='utf-8', newline='\n')
        return source

    def test_arguments_and_distinct_default_workspaces(self):
        for profile in build.COMMITS:
            args = build.parse_args([profile, '--msys2-dir', 'D:/中文工具/msys64'])
            self.assertEqual(args.work_dir, ROOT / '.build' / f'{profile}-reference')
            self.assertEqual(args.jobs, 4)
            explicit = build.parse_args([profile, '--msys2-dir', 'D:/msys64',
                                         '--work-dir', '独立目录', '--jobs', '32'])
            self.assertEqual(explicit.work_dir, Path('独立目录'))
            self.assertEqual(explicit.jobs, 32)
        for argv in (['z72'], ['other', '--msys2-dir', 'x'],
                     ['z62', '--msys2-dir', 'x', '--jobs', '0'],
                     ['z62', '--msys2-dir', 'x', '--jobs', '33'],
                     ['z62', '--msys2-dir', 'x', '--jobs', 'oops']):
            with self.subTest(argv=argv), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    build.parse_args(argv)

    def test_minimal_offline_configuration_and_exact_pins(self):
        self.assertEqual(build.COMMITS, {
            'z72': 'f6b80ec650116a6b0117d31f9ea112b05bb7f52a',
            'z62': '4f4389944fc339d107f22f5f7ca3f90cc34b78de'})
        self.assertEqual(build.upstream.ARCHIVE_SHA256,
                         '821b545b92f165e57dddccac5077d76d4d436a226595b8813ad59306bbfd0746')
        self.assertEqual(build.CONFIGURE, [*build.upstream.CONFIGURE, '--enable-pixman'])
        for flag in ('--disable-download', '--without-default-devices', '--without-default-features',
                     '--target-list=arm-softmmu', '--enable-fdt', '--enable-tcg', '--enable-pixman'):
            self.assertIn(flag, build.CONFIGURE)

    def test_workspace_guards_preserve_existing_files(self):
        cases = ('converted', 'mismatch', 'invalid', 'matching', 'runtime', 'source', 'file')
        with self.temp() as folder:
            root = Path(folder)
            for case in cases:
                with self.subTest(case=case):
                    work = root / case
                    if case == 'file':
                        work.write_bytes(b'keep')
                    else:
                        work.mkdir()
                        if case == 'converted':
                            (work / build.CONVERSION_MARKER).write_text('converted to Z62', encoding='utf-8')
                        elif case in ('mismatch', 'matching', 'invalid'):
                            data = 'bad json' if case == 'invalid' else json.dumps(
                                build.identity('z62' if case == 'mismatch' else 'z72'))
                            (work / build.MARKER).write_text(data, encoding='utf-8')
                        else:
                            target = work / case / 'keep.exe'
                            target.parent.mkdir()
                            target.write_bytes(b'running executable or unknown source')
                    before = build.tree_hashes(root)
                    with self.assertRaisesRegex(ValueError, 'new --work-dir'):
                        build.guard_workspace(work, 'z72')
                    self.assertEqual(build.tree_hashes(root), before)
            fresh = root / '新目录'
            self.assertEqual(build.guard_workspace(fresh, 'z62'), fresh.resolve())
            self.assertFalse(fresh.exists())
            empty = root / 'empty'
            empty.mkdir()
            self.assertEqual(build.guard_workspace(empty, 'z62'), empty.resolve())

    def test_conversion_and_profile_ancestors_are_protected(self):
        with self.temp() as folder:
            root = Path(folder)
            old = root / '.build/z72-reference'
            old.mkdir(parents=True)
            with patch.object(build, 'ROOT', root):
                with self.assertRaisesRegex(ValueError, 'nest'):
                    build.guard_workspace(old / 'source/new', 'z62')
                (old / build.CONVERSION_MARKER).write_text('Z62 conversion', encoding='utf-8')
                for profile in build.COMMITS:
                    with self.assertRaisesRegex(ValueError, 'Converted'):
                        build.guard_workspace(old / 'new', profile)

    def test_bad_source_marker_rejected_before_any_build_work(self):
        with self.temp() as folder:
            work = Path(folder)
            (work / build.MARKER).write_text(json.dumps(build.identity('z72')), encoding='utf-8')
            args = build.parse_args(['z62', '--msys2-dir', 'missing', '--work-dir', str(work)])
            with patch.object(build.upstream, 'unpack') as unpack, patch.object(build, 'run_build') as compile_qemu:
                with self.assertRaisesRegex(ValueError, 'mismatch'):
                    build.build_reference(args)
                unpack.assert_not_called()
                compile_qemu.assert_not_called()

    def test_repository_pins_and_tracked_clean_guards(self):
        for profile in build.COMMITS:
            self.assertEqual(build.verify_repository(profile), ROOT / 'third_party' / f'{profile}-qemu')
        with patch.object(build.subprocess, 'check_output', return_value='0' * 40):
            with self.assertRaisesRegex(ValueError, 'commit'):
                build.verify_repository('z72')
        with patch.object(build.subprocess, 'check_output', return_value=build.COMMITS['z62']), \
                patch.object(build.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, 'git diff')) as run:
            with self.assertRaisesRegex(ValueError, 'tracked changes'):
                build.verify_repository('z62')
            self.assertEqual(run.call_args.args[0][-4:], ['diff', '--quiet', 'HEAD', '--'])

    def test_sole_compatibility_fix_is_exact_and_preserves_line_endings(self):
        for profile in build.COMMITS:
            original = (ROOT / 'third_party' / f'{profile}-qemu/qemu/nikon-z72.c').read_bytes()
            changed = build.compatible_board(original)
            self.assertEqual(changed, original.replace(build.OLD, build.NEW, 1))
            self.assertEqual(changed.replace(build.NEW, build.OLD, 1), original)
            self.assertEqual(changed.count(build.NEW), 1)
            crlf = original.replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')
            self.assertEqual(build.compatible_board(crlf), crlf.replace(build.OLD, build.NEW, 1))
            invalid = (changed, original + build.OLD, original.replace(build.OLD, b'changed'),
                       original.replace(b'uint32_t frame_count;', b'uint64_t frame_count;'),
                       original.replace(b'OBJ_PROP_FLAG_READ', b'OBJ_PROP_FLAG_WRITE'))
            for data in invalid:
                with self.assertRaisesRegex(ValueError, 'refusing'):
                    build.compatible_board(data)

    def test_real_donor_interfaces_prepare_only_expected_overlay(self):
        for profile in build.COMMITS:
            with self.subTest(profile=profile), self.temp() as folder:
                work = Path(folder)
                repo = build.verify_repository(profile)
                hashes = build.snapshot_donor(repo, work / 'donor')
                self.assertIn('qemu/prepare_source.py', hashes)
                self.assertFalse(any('__pycache__' in name for name in hashes))
                source = self.scaffold(work / 'source')
                donor_before = build.tree_hashes(work / 'donor')
                build.prepare_source(source, work / 'donor')
                self.assertEqual(donor_before, build.tree_hashes(work / 'donor'))
                self.assertIn('g_malloc_n(height, stride)', (source / 'ui/ui-qmp-cmds.c').read_text())
                self.assertIn('CONFIG_NIKON_Z72_LAB=y',
                              (source / 'configs/devices/arm-softmmu/default.mak').read_text())
                self.assertEqual((source / 'hw/arm/nikon-z72.c').read_bytes(),
                                 build.compatible_board((repo / 'qemu/nikon-z72.c').read_bytes()))
                self.assertFalse((source / 'target').exists())
                self.assertFalse((source / 'hw/arm/nikon-z6ii.c').exists())

    def test_configuration_wrapper_restores_primary_builder_after_failure(self):
        previous = build.upstream.CONFIGURE
        def fail(*args):
            self.assertEqual(build.upstream.CONFIGURE, build.CONFIGURE)
            raise RuntimeError('simulated build error; no compilation')
        with patch.object(build.upstream, 'run_build', side_effect=fail):
            with self.assertRaises(RuntimeError):
                build.run_build(Path('source'), Path('build'), Path('msys'), 4)
        self.assertIs(build.upstream.CONFIGURE, previous)

    def test_device_configuration_is_verified(self):
        with self.temp() as folder:
            root = Path(folder)
            config = root / 'arm-softmmu-config-devices.h'
            config.write_text(DEVICE_DEFINES, encoding='utf-8')
            build.verify_devices(root)
            config.write_text(DEVICE_DEFINES.replace('#define CONFIG_SD 1\n', ''), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'CONFIG_SD'):
                build.verify_devices(root)

    def test_smoke_checks_use_clean_path_and_only_help(self):
        for profile in build.COMMITS:
            machine = build.MACHINES[profile]
            output = [b'QEMU emulator version 10.2.4', machine.encode(),
                      (machine + '-machine options:').encode(), b'sd-card options:']
            results = [subprocess.CompletedProcess([], 0, item, b'') for item in output]
            with patch.object(build.subprocess, 'run', side_effect=results) as run:
                checks = build.smoke_checks(Path('D:/runtime/qemu-system-arm.exe'), profile)
            expected = [['--version'], ['-M', 'help'], ['-M', machine + ',help']]
            if profile == 'z62':
                expected.append(['-device', 'sd-card,help'])
            self.assertEqual([call.args[0][1:] for call in run.call_args_list], expected)
            self.assertEqual(len(checks), len(expected))
            for call in run.call_args_list:
                self.assertEqual(call.kwargs['env']['PATH'],
                                 str(Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'System32'))
                self.assertTrue(call.kwargs['check'])
                self.assertEqual(call.kwargs['timeout'], 60)
        bad = subprocess.CompletedProcess([], 0, b'wrong', b'')
        with patch.object(build.subprocess, 'run', return_value=bad):
            with self.assertRaisesRegex(ValueError, 'version/machine'):
                build.smoke_checks(Path('D:/runtime/qemu-system-arm.exe'), 'z72')

    def test_archive_guard_precedes_extraction_and_directory_creation(self):
        with self.temp() as folder:
            root = Path(folder)
            msys = root / 'msys64'
            for name in ('usr/bin/bash.exe', 'ucrt64/bin/gcc.exe', 'ucrt64/bin/objdump.exe'):
                path = msys / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'not executed')
            args = build.parse_args(['z62', '--msys2-dir', str(msys), '--work-dir', str(root / 'new')])
            with patch.object(build, 'ROOT', root), patch.object(build.sys, 'platform', 'win32'), \
                    patch.object(build, 'verify_repository'), patch.object(build.upstream, 'unpack') as unpack:
                with self.assertRaisesRegex(ValueError, 'cached upstream archive'):
                    build.build_reference(args)
                archive = root / '.build/downloads/qemu-10.2.4.tar.xz'
                archive.parent.mkdir(parents=True)
                archive.write_bytes(b'wrong archive')
                with self.assertRaisesRegex(ValueError, 'SHA-256 mismatch'):
                    build.build_reference(args)
                self.assertFalse(args.work_dir.exists())
                unpack.assert_not_called()

    def test_mock_build_pipeline_manifest_and_no_overwrite(self):
        # Real donor preparation, fake archive extraction/compiler/DLL staging/help.
        for profile in build.COMMITS:
            with self.subTest(profile=profile), self.temp() as folder:
                root = Path(folder)
                repo = build.verify_repository(profile)
                msys = root / '工具链'
                for name in ('usr/bin/bash.exe', 'ucrt64/bin/gcc.exe', 'ucrt64/bin/objdump.exe'):
                    path = msys / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(b'not executed')
                archive = root / '.build/downloads/qemu-10.2.4.tar.xz'
                archive.parent.mkdir(parents=True)
                archive.write_bytes(b'fake archive, never extracted')
                (root / 'tools').mkdir()
                (root / 'tools/build_qemu.py').write_bytes(b'fixture builder identity')
                args = build.parse_args([profile, '--msys2-dir', str(msys),
                                         '--work-dir', str(root / f'{profile}-新建'), '--jobs', '8'])
                def unpack(_archive, destination):
                    return self.scaffold(destination / 'qemu-10.2.4')
                def compile_qemu(source, destination, toolchain, jobs):
                    self.assertEqual(source, args.work_dir / 'source/qemu-10.2.4')
                    self.assertEqual(toolchain, msys.resolve())
                    self.assertEqual(jobs, 8)
                    destination.mkdir()
                    (destination / 'arm-softmmu-config-devices.h').write_text(DEVICE_DEFINES, encoding='utf-8')
                    binary = destination / 'qemu-system-arm.exe'
                    binary.write_bytes(b'fake binary; not executable')
                    return binary
                def stage(binary, _msys, destination):
                    shutil.copyfile(binary, destination / binary.name)
                    (destination / 'pixman.dll').write_bytes(b'fake DLL')
                    return {'pixman.dll': build.upstream.digest(destination / 'pixman.dll')}
                with patch.object(build, 'ROOT', root), patch.object(build.sys, 'platform', 'win32'), \
                        patch.object(build, 'verify_repository', return_value=repo), \
                        patch.object(build.upstream, 'ARCHIVE_SHA256', build.upstream.digest(archive)), \
                        patch.object(build.upstream, 'unpack', side_effect=unpack), \
                        patch.object(build, 'run_build', side_effect=compile_qemu) as compiler, \
                        patch.object(build.upstream, 'stage_windows', side_effect=stage), \
                        patch.object(build, 'smoke_checks', return_value={'host_only': 'mocked'}):
                    manifest = build.build_reference(args)
                    saved = json.loads((args.work_dir / 'reference-build-manifest.json').read_text(encoding='utf-8'))
                    self.assertEqual(saved, manifest)
                    self.assertEqual(manifest['donor_commit'], build.COMMITS[profile])
                    self.assertEqual(manifest['configure'], build.CONFIGURE)
                    self.assertEqual(manifest['binary_sha256'],
                                     build.upstream.digest(args.work_dir / 'runtime/qemu-system-arm.exe'))
                    self.assertIn('pixman.dll', manifest['runtime_dll_sha256'])
                    self.assertIn('qemu/prepare_source.py', manifest['donor_file_sha256'])
                    self.assertIn('hw/arm/nikon-z72.c', manifest['prepared_source_file_sha256'])
                    self.assertEqual(manifest['compatibility_changes'], [build.COMPATIBILITY])
                    for key in ('firmware_run', 'guest_patched', 'cpu_patched'):
                        self.assertFalse(manifest[key])
                    before = build.tree_hashes(args.work_dir)
                    with self.assertRaisesRegex(ValueError, 'protected'):
                        build.build_reference(args)
                    self.assertEqual(build.tree_hashes(args.work_dir), before)
                    compiler.assert_called_once()


if __name__ == '__main__':
    unittest.main()
