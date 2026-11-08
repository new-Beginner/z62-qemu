"""r14 fixture provenance/containment tests; no model or camera launch."""
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import z62_reconstructed_fixtures as fixtures


class ReconstructedFixtureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ['PI_SCRATCH_DIR'])
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)

    def test_extra_pixel_header_is_explicitly_included(self):
        key = 'qemu/z62-mode-geometry/nikon-z62-mode-grid-pixels.h'
        prepared = json.loads((fixtures.MODEL / 'prepared.json').read_text())
        self.assertIn(key, fixtures.dependencies())
        self.assertEqual(fixtures.dependencies()[key],
                         prepared['source_sha256']['hw/arm/nikon-z62-mode-grid-pixels.h'])

    def test_no_old_or_nested_output_is_accepted(self):
        root = fixtures.ROOT
        for path in (root / '.build/z62-capcom-2026.10.28-r6',
                     root / '.build/fenestra-z62-fixtures-r14-01',
                     root / '.build/fenestra-z62-fixtures-r14-other/nested'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                fixtures.guard(path)
        path = root / '.build/fenestra-z62-fixtures-r14-uncreated-unit'
        self.assertEqual(fixtures.guard(path), path.resolve())
        self.assertFalse(path.exists())

    def test_layer_refuses_changed_input(self):
        root = self.folder / 'hw/arm'
        root.mkdir(parents=True)
        (root / 'a.c').write_bytes(b'changed')
        module = types.SimpleNamespace(INPUTS={'a.c': fixtures.model.sha(b'original')})
        with self.assertRaisesRegex(ValueError, 'frozen input'):
            fixtures.layer_inputs('unit', module, self.folder)
        self.assertEqual((root / 'a.c').read_bytes(), b'changed')

    def test_current_map_uses_only_exact_verified_input_files(self):
        work = fixtures.ROOT / '.build/fenestra-z62-fixtures-r14-01'
        mapping = fixtures.read_mapping(work)
        self.assertGreater(len(mapping), 8)
        for old, (new, digest) in mapping.items():
            self.assertTrue(old.is_relative_to(fixtures.ROOT / '.build'))
            self.assertTrue(new.is_relative_to(work))
            self.assertEqual(fixtures.model.sha(new.read_bytes()), digest)
            self.assertFalse(old.exists(), 'Test adapter must not create old source files')

    def test_changed_manifest_recipe_is_rejected(self):
        path = self.folder / 'fixture-manifest.json'
        path.write_text(json.dumps({'version': fixtures.VERSION, 'dependencies_sha256': {}}))
        with self.assertRaisesRegex(ValueError, 'identity changed'):
            fixtures.read_mapping(self.folder)

    def test_fixture_escape_is_rejected(self):
        work = fixtures.ROOT / '.build/fenestra-z62-fixtures-r14-01'
        record = json.loads((work / 'fixture-manifest.json').read_text())
        row = next(iter(record['fixtures']['capcom'].values()))
        row['path'] = '../outside.c'
        (self.folder / 'fixture-manifest.json').write_text(json.dumps(record))
        with self.assertRaisesRegex(ValueError, 'escaped or changed'):
            fixtures.read_mapping(self.folder)

    def test_existing_test_output_is_not_overwritten(self):
        output = fixtures.ROOT / 'analysis/fenestra-z62-model-r14/legacy-with-fixtures-1.json'
        before = output.read_bytes()
        with self.assertRaisesRegex(ValueError, 'new r14 test output'):
            fixtures.run_tests(fixtures.ROOT / '.build/fenestra-z62-fixtures-r14-01', output)
        self.assertEqual(output.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
