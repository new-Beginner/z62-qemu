"""r13 builder guards and provenance tests; no compiler, firmware or camera."""
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import rebuild_fenestra_z62_model as model


class ModelRebuildTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ['PI_SCRATCH_DIR'])
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_transaction_transform_body_matches_original(self):
        model.check_transaction_body()

    def test_guard_allows_only_new_direct_versioned_workspace(self):
        with patch.object(model, 'ROOT', self.root):
            (self.root / '.build').mkdir()
            path = self.root / '.build/fenestra-z62-model-r13-unit'
            self.assertEqual(model.guard(path, True), path.resolve())
            for bad in (self.root / 'elsewhere', self.root / '.build/z62-output-lineage-2026.11.03-r69',
                        path / 'nested'):
                with self.assertRaises(ValueError):
                    model.guard(bad, True)
            path.mkdir()
            with self.assertRaisesRegex(ValueError, 'immutable'):
                model.guard(path, True)
            self.assertEqual(model.guard(path, False), path.resolve())

    def test_guard_refuses_linked_ancestor(self):
        with patch.object(Path, 'is_junction', return_value=True):
            with self.assertRaisesRegex(ValueError, 'Linked'):
                model.guard(self.root, True)

    def test_exact_tree_rejects_changed_missing_and_extra(self):
        (self.root / 'a').write_bytes(b'original')
        expected = {'a': model.sha(b'original')}
        model.verify_tree(self.root, expected)
        for actual in ({'a': '0' * 64}, {}, {'a': expected['a'], 'extra': expected['a']}):
            with self.assertRaisesRegex(ValueError, 'differs'):
                model.verify_tree(self.root, actual)

    def test_output_json_is_exclusive(self):
        p = self.root / 'out.json'
        model.save(p, {'valid': True})
        before = p.read_bytes()
        with self.assertRaises(FileExistsError):
            model.save(p, {'valid': False})
        self.assertEqual(p.read_bytes(), before)

    def test_layer_rejects_wrong_input_without_render_or_write(self):
        arm = self.root / 'hw/arm'
        arm.mkdir(parents=True)
        target = arm / 'a.c'
        target.write_bytes(b'bad')
        mod = types.SimpleNamespace(INPUTS={'a.c': model.sha(b'good')})
        with self.assertRaisesRegex(ValueError, 'Frozen layer input'):
            model.render_layer('fake', mod, self.root)
        self.assertEqual(target.read_bytes(), b'bad')

    def test_renderer_outputs_and_header_are_recorded(self):
        arm = self.root / 'hw/arm'
        arm.mkdir(parents=True)
        (arm / 'a.c').write_bytes(b'good')
        header = self.root / 'new.h'
        header.write_bytes(b'header')
        mod = types.SimpleNamespace(INPUTS={'a.c': model.sha(b'good')}, VERSION='test',
                                    HEADER=header, identity=lambda: {'test': True},
                                    render=lambda files: {'a.c': 'changed'})
        result = model.render_layer('fake', mod, self.root)
        self.assertEqual(result['input_sha256'], mod.INPUTS)
        self.assertEqual(result['output_sha256'], {'hw/arm/a.c': model.sha(b'changed'),
                                                    'hw/arm/new.h': model.sha(b'header')})

    def test_renderer_escape_rejected(self):
        arm = self.root / 'hw/arm'
        arm.mkdir(parents=True)
        (arm / 'a').write_bytes(b'a')
        mod = types.SimpleNamespace(INPUTS={'a': model.sha(b'a')},
                                    render=lambda files: {'../../../outside': b'bad'})
        with self.assertRaisesRegex(ValueError, 'escapes'):
            model.render_layer('fake', mod, self.root)
        self.assertFalse((self.root.parent / 'outside').exists())

    def test_compile_command_offline_scratch_and_jobs(self):
        source, build = self.root / 'source', self.root / 'build'
        cmd, env = model.build_command(source, build, self.root / 'msys', 2)
        script = cmd[-1]
        self.assertIn('--disable-download', script)
        self.assertIn('PIP_NO_INDEX=1', script)
        self.assertIn(model.reference.upstream.msys_path(model.scratch_root()), script)
        self.assertNotIn('TMP=/tmp', script)
        self.assertIn('ninja -j 2 qemu-system-arm.exe', script)
        self.assertEqual(env['TEMP'], str(model.scratch_root()))
        for bad in (0, 33):
            with self.assertRaises(ValueError):
                model.build_command(source, build, self.root, bad)

    def test_scratch_is_required(self):
        with patch.dict(os.environ, {'PI_SCRATCH_DIR': ''}):
            with self.assertRaisesRegex(ValueError, 'PI_SCRATCH_DIR'):
                model.scratch_root()

    def test_recipe_covers_all_adapters_and_headers(self):
        files = model.recipe_files()
        for module in model.modules():
            self.assertIn(Path(module.__file__).relative_to(model.ROOT).as_posix(), files)
            if hasattr(module, 'HEADER'):
                self.assertIn(module.HEADER.relative_to(model.ROOT).as_posix(), files)
        self.assertEqual(len(model.CHAIN), 23)

    def test_toolchain_stage_path_must_be_ascii_scratch_child(self):
        allowed = model.scratch_root() / 'msys-r13-test'
        self.assertEqual(model.guard_toolchain_stage(allowed), allowed)
        for bad in (model.ROOT / '.runtime/tools/msys64', model.scratch_root(),
                    model.scratch_root() / 'msys-r13-中文'):
            with self.assertRaises(ValueError):
                model.guard_toolchain_stage(bad)

    def test_meson_lock_is_explicit_and_exclusive(self):
        (self.root / 'subprojects').mkdir()
        model.prepare_meson_lock(self.root)
        lock = self.root / 'subprojects/.wraplock'
        self.assertEqual(lock.read_bytes(), b'')
        with self.assertRaises(FileExistsError):
            model.prepare_meson_lock(self.root)

    def test_prior_build_is_never_resumed(self):
        with patch.object(model, 'ROOT', self.root):
            work = self.root / '.build/fenestra-z62-model-r13-unit'
            work.mkdir(parents=True)
            (work / 'build-attempt.json').write_text('{}')
            with self.assertRaisesRegex(ValueError, 'immutable'):
                model.compile_model(work, 2)


if __name__ == '__main__':
    unittest.main()
