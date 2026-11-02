"""Decoder work must not hold the live card lock; status keeps a small catalog."""
from importlib.util import find_spec
from pathlib import Path
import sys
import tempfile
import threading
import time
from unittest.mock import patch
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from z62_video_codec import VideoRecorder
from test_z62_video_codec import frame


@unittest.skipUnless(find_spec('av'), 'Optional video profile requires the isolated video Python')
class AsyncVideoCardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as directory:
            recorder = VideoRecorder(Path(directory), start_ns=0, clock_epoch='video-test')
            try:
                recorder.append(frame('red', 10_000_000, 1))
                recorder.append(frame('blue', 70_000_000, 2))
                cls.movie = recorder.finish(100_000_000)
            finally:
                recorder.abort()

    def setUp(self):
        try:
            import z62_async_video_card as api
        except ImportError as exc:
            self.fail('The nonblocking validated video card is missing: ' + str(exc))
        self.api = api
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.card = api.AsyncVideoCard.create(Path(self.temp.name) / 'card')
        self.addCleanup(self.card.close)

    def test_status_does_not_wait_for_the_external_video_validator(self):
        entered, release = threading.Event(), threading.Event()
        validate = self.api.validate_video_metadata
        errors = []

        def slow_validator(*args):
            entered.set()
            if not release.wait(8):
                raise RuntimeError('test validator gate was not released')
            return validate(*args)

        def store():
            try:
                self.card.store_video(**self.movie)
            except Exception as exc:
                errors.append(exc)

        with patch.object(self.api, 'validate_video_metadata', slow_validator):
            thread = threading.Thread(target=store)
            thread.start()
            try:
                self.assertTrue(entered.wait(5))
                started = time.monotonic()
                self.assertEqual(self.card.summary()['videos'], 0)
                self.assertLess(time.monotonic() - started, .5)
            finally:
                release.set()
                thread.join(15)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(self.card.summary()['videos'], 1)

    def test_gui_catalog_is_compact_but_explicit_details_and_reopen_are_complete(self):
        saved = self.card.store_video(**self.movie)
        summary = self.card.summary()['images'][0]
        self.assertEqual(summary['metadata']['frame_count'], 2)
        self.assertNotIn('samples', summary['metadata'])
        self.assertNotIn('independent_audit', summary['metadata'])
        detail = self.card.full_item(saved['name'])
        self.assertEqual(len(detail['metadata']['samples']), 2)
        self.assertEqual(self.card.read(saved['name']), self.movie['video'])
        self.card.close()
        with self.api.AsyncVideoCard(Path(self.temp.name) / 'card') as reopened:
            self.assertEqual(len(reopened.full_item(saved['name'])['metadata']['samples']), 2)
            self.assertEqual(reopened.summary()['videos'], 1)

    def test_commit_failure_leaves_no_movie_or_poster_and_keeps_number(self):
        with patch.object(self.api.os, 'replace', side_effect=OSError('catalog write failed')):
            with self.assertRaises(OSError):
                self.card.store_video(**self.movie)
        self.assertEqual(self.card.list(), [])
        self.assertEqual(list(self.card.image_directory.iterdir()), [])
        self.assertEqual(self.card.store_video(**self.movie)['name'], 'Z62_0001.MP4')

    def test_unowned_result_cannot_bypass_validation(self):
        with self.assertRaises(ValueError):
            self.card.commit_verified({'validated': True, **self.movie})
        self.assertEqual(self.card.list(), [])


if __name__ == '__main__':
    unittest.main()
