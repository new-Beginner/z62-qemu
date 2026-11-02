# SPDX-License-Identifier: GPL-2.0-or-later
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import probe_z62_transaction as probe


class EvidenceTests(unittest.TestCase):
    def test_existing_file_rejected_before_running(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get('PI_SCRATCH_DIR')) as folder:
            out = Path(folder) / 'evidence.json'
            original = b'{"old":true}\n'
            out.write_bytes(original)
            with patch.object(probe, 'run') as run, self.assertRaises(FileExistsError):
                probe.run_to_file(Path('unused.exe'), out)
            run.assert_not_called()
            self.assertEqual(out.read_bytes(), original)

    def test_atomic_publication_does_not_replace_competing_file(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get('PI_SCRATCH_DIR')) as folder:
            out = Path(folder) / 'evidence.json'
            probe.publish_exclusive(out, {'complete': True})
            original = out.read_bytes()
            self.assertEqual(json.loads(original), {'complete':True})
            with self.assertRaises(FileExistsError):
                probe.publish_exclusive(out, {'replacement':True})
            self.assertEqual(out.read_bytes(), original)
            self.assertEqual(list(Path(folder).iterdir()), [out])

    def test_failure_is_recorded_but_not_claimed_complete(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get('PI_SCRATCH_DIR')) as folder:
            out = Path(folder) / 'new/evidence.json'
            with patch.object(probe, 'run', side_effect=TimeoutError('fixture QMP timeout')), \
                 self.assertRaisesRegex(TimeoutError, 'fixture QMP timeout'):
                probe.run_to_file(Path('unused.exe'), out)
            result = json.loads(out.read_text())
            self.assertFalse(result['completed'])
            self.assertEqual(result['failure']['type'], 'TimeoutError')


if __name__ == '__main__':
    unittest.main()
