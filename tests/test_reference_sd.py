"""Host SD passthrough under the r73 workspace entry's real path adaptation.

Only Path is adapted, exactly as run_z62_workspace does. Validation and IO are
real; the frozen legacy entry keeps its original ASCII-only behavior.
"""
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import run_reference_console as run
import z62_workspace_paths as storage


class ReferenceSDTests(unittest.TestCase):
    def setUp(self):
        # A physical ASCII checkout needs no SUBST adaptation.
        path_type=Path if str(storage.ROOT).isascii() else storage.WorkspacePath
        transport=patch.object(run,'Path',path_type)
        transport.start(); self.addCleanup(transport.stop)

    def temp(self):
        return tempfile.TemporaryDirectory(dir=os.environ.get('PI_SCRATCH_DIR'))

    def test_no_card_is_default(self):
        self.assertIsNone(run.validate_sd_card('z62', None))
        self.assertIsNone(run.validate_sd_card('z72', None))

    def test_regular_aligned_image_is_preserved(self):
        with self.temp() as folder:
            p = Path(folder) / 'card with spaces.img'
            p.write_bytes(b'x' * 1024)
            self.assertEqual(Path(run.validate_sd_card('z62', p)).resolve(), p.resolve())
            self.assertEqual(p.read_bytes(), b'x' * 1024)

    def test_invalid_images_and_profiles_are_rejected(self):
        with self.temp() as folder:
            root = Path(folder)
            for name, size in [('empty.img', 0), ('short.img', 513),
                               ('card,snapshot=off.img', 512), ('中文.img', 512)]:
                p = root / name
                p.write_bytes(b'x' * size)
                with self.subTest(name=name), self.assertRaises(ValueError):
                    run.validate_sd_card('z62', p)
            for p in (root, root / 'missing.img'):
                with self.assertRaises(ValueError):
                    run.validate_sd_card('z62', p)
            with self.assertRaises(ValueError):
                run.validate_sd_card('z72', root / 'empty.img')

    def test_cli_passthrough_and_session_record(self):
        for attach in (False, True):
            with self.subTest(attach=attach), self.temp() as folder:
                root = Path(folder)
                image = root / 'card.img'
                image.write_bytes(b'\0' * 512)
                argv = ['run', 'z62', '--experimental-parameters']
                if attach:
                    argv += ['--sd-card', str(image)]
                captured = []
                old_path = list(sys.path)
                try:
                    with patch.object(sys, 'argv', argv), \
                            patch.object(run, 'stage', return_value=(root, {'parameters': None})), \
                            patch.object(run, 'install_native_process_adapter', return_value=run.subprocess.Popen), \
                            patch.object(run.runpy, 'run_path', side_effect=lambda *a, **k: captured.extend(sys.argv)), \
                            contextlib.redirect_stdout(io.StringIO()):
                        run.main()
                finally:
                    sys.path[:] = old_path
                record = json.loads((root / 'session.json').read_text(encoding='utf-8'))
                self.assertEqual(record['host_version'], run.HOST_VERSION)
                if attach:
                    self.assertEqual(Path(captured[captured.index('--sd-card') + 1]).resolve(), image.resolve())
                    self.assertTrue(record['sd_card']['snapshot'])
                    self.assertFalse(record['sd_card']['persistent_guest_writes'])
                    self.assertFalse(record['sd_card']['filesystem_verified'])
                else:
                    self.assertNotIn('--sd-card', captured)
                    self.assertIsNone(record['sd_card'])
                self.assertNotIn('--main-screen-experiment', captured)

    def test_invalid_cli_fails_before_staging(self):
        with patch.object(sys, 'argv', ['run', 'z72', '--sd-card', 'missing.img']), \
                patch.object(run, 'stage') as stage, contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as exc:
                run.main()
            self.assertEqual(exc.exception.code, 2)
            stage.assert_not_called()


if __name__ == '__main__':
    unittest.main()
