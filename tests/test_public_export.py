from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))


class PublicExportTests(unittest.TestCase):
    def api(self):
        try:
            import export_z62_public as exporter
        except ImportError as exc:
            self.fail('Public source export is missing: ' + str(exc))
        return exporter

    def fixture(self, folder):
        root = Path(folder)/'source'
        (root/'tools').mkdir(parents=True)
        (root/'tools/example.py').write_bytes(b'VALUE = 1\r\n')
        (root/'qemu').mkdir()
        (root/'qemu/model.h').write_bytes(b'/* GPL-2.0-or-later */\n')
        (root/'stock.bin').write_bytes(b'private firmware')
        (root/'analysis/run').mkdir(parents=True)
        (root/'analysis/run/trace.json').write_text('{"memory": "private raw dump"}', encoding='utf-8')
        (root/'analysis/run/report.json').write_text('{"completed": false}', encoding='utf-8')
        (root/'2026-11-02_test-report.md').write_text(
            '[source](tools/example.py:1) [dump](analysis/run/trace.json)\n', encoding='utf-8')
        return root, Path(folder)/'public'

    def test_source_bytes_and_failure_summary_are_preserved_without_firmware(self):
        module = self.api()
        with tempfile.TemporaryDirectory() as folder:
            root, target = self.fixture(folder)
            result = module.export(root, target)
            self.assertEqual((target/'tools/example.py').read_bytes(), b'VALUE = 1\r\n')
            self.assertFalse((target/'stock.bin').exists())
            self.assertFalse((target/'analysis/run/trace.json').exists())
            self.assertTrue((target/'analysis/run/report.json').is_file())
            self.assertGreater(result['file_count'], 0)
            self.assertEqual((root/'stock.bin').read_bytes(), b'private firmware')

    def test_moved_report_links_are_valid_and_omitted_dump_is_plain_text(self):
        module = self.api()
        with tempfile.TemporaryDirectory() as folder:
            root, target = self.fixture(folder)
            module.export(root, target)
            text = (target/'docs/history/2026-11-02_test-report.md').read_text(encoding='utf-8')
            self.assertIn('../../tools/example.py#L1', text)
            self.assertNotIn('](analysis/run/trace.json)', text)
            self.assertIn('analysis/run/trace.json', text)

    def test_existing_output_and_output_inside_source_are_rejected(self):
        module = self.api()
        with tempfile.TemporaryDirectory() as folder:
            root, target = self.fixture(folder)
            target.mkdir()
            (target/'keep.txt').write_text('keep', encoding='utf-8')
            with self.assertRaises(ValueError): module.export(root, target)
            with self.assertRaises(ValueError): module.export(root, root/'nested')
            self.assertEqual((target/'keep.txt').read_text(encoding='utf-8'), 'keep')

    def test_credential_in_source_is_rejected_before_any_output(self):
        module = self.api()
        with tempfile.TemporaryDirectory() as folder:
            root, target = self.fixture(folder)
            (root/'tools/leak.py').write_text('VALUE = "' + 'gh' + 'p_' + 'A'*36 + '"', encoding='utf-8')
            with self.assertRaises(ValueError): module.export(root, target)
            self.assertFalse(target.exists())

    def test_private_paths_are_redacted_in_documentation(self):
        module = self.api()
        text = module.scrub('C:/Users/private-user/Documents/run ' + str(Path.cwd()), Path.cwd())
        self.assertNotIn('private-user', text)
        self.assertNotIn(str(Path.cwd()), text)
