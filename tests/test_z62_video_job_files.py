"""Windows progress publication retries sharing violations without lying about state."""
import json
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import z62_async_video_job as jobs


class VideoJobFileTests(unittest.TestCase):
    def test_transient_sharing_conflict_preserves_old_state_then_publishes_new_state(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'progress.json'
            jobs.atomic_json(path, {'frames': 1})
            replace = jobs.os.replace
            failures = [True, True, False]

            def sharing_violation(source, target):
                if failures.pop(0):
                    self.assertEqual(json.loads(path.read_bytes()), {'frames': 1})
                    raise PermissionError('simulated Windows file sharing conflict')
                return replace(source, target)

            try:
                with patch.object(jobs.os, 'replace', side_effect=sharing_violation):
                    jobs.atomic_json(path, {'frames': 2})
            except PermissionError as exc:
                self.fail('A transient progress-file sharing conflict must be retried: ' + str(exc))
            self.assertEqual(json.loads(path.read_bytes()), {'frames': 2})
            self.assertEqual([p.name for p in Path(directory).iterdir()], ['progress.json'])

    def test_persistent_conflict_is_bounded_and_does_not_replace_or_fake_the_old_state(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'progress.json'
            jobs.atomic_json(path, {'frames': 1})
            started = time.monotonic()
            with patch.object(jobs.os, 'replace', side_effect=PermissionError('persistent sharing conflict')):
                with self.assertRaises(PermissionError):
                    jobs.atomic_json(path, {'frames': 2})
            self.assertLess(time.monotonic() - started, 2)
            self.assertEqual(json.loads(path.read_bytes()), {'frames': 1})
            self.assertEqual([p.name for p in Path(directory).iterdir()], ['progress.json'])


if __name__ == '__main__':
    unittest.main()
