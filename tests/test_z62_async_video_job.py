"""Owned subprocess completion, cancellation, integrity and atomic publication."""
from importlib.util import find_spec
from pathlib import Path
import os
import sys
import tempfile
import threading
import time
from unittest.mock import patch
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from z62_video_codec import VideoRecorder
from z62_async_video_card import AsyncVideoCard
from test_z62_video_codec import frame

FIXTURE = Path(__file__).with_name('helpers') / 'video_worker_fixture.py'


@unittest.skipUnless(find_spec('av'), 'Optional video profile requires the isolated video Python')
class AsyncVideoJobTests(unittest.TestCase):
    def setUp(self):
        try:
            import z62_async_video_job as api
        except ImportError as exc:
            self.fail('The owned cancellable video job is missing: ' + str(exc))
        self.api = api
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'jobs').mkdir()
        self.card = AsyncVideoCard.create(self.root / 'card')
        self.addCleanup(self.card.close)
        self.recorder = VideoRecorder(self.root, start_ns=0, clock_epoch='video-test')
        self.addCleanup(self.recorder.abort)
        self.recorder.append(frame('red', 10_000_000, 1))
        self.recorder.append(frame('blue', 70_000_000, 2))
        self.job = None

    def launch(self, *, timeout_s=60):
        self.job = self.api.VideoJob(self.recorder, self.card, self.root / 'jobs', stop_ns=100_000_000,
                                    timeout_s=timeout_s)
        self.addCleanup(lambda: self.job.close(timeout=15))
        self.job.start()
        return self.job

    def wait(self, predicate, seconds=15):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            state = self.job.snapshot()
            if predicate(state):
                return state
            time.sleep(.02)
        self.fail('Job did not reach required state: ' + str(self.job.snapshot()))

    def fault(self, mode):
        return (patch.object(self.api, 'WORKER_SCRIPT', FIXTURE),
                patch.dict('os.environ', {'Z62_ASYNC_TEST_MODE': mode}))

    def test_real_worker_encodes_validates_and_commits_before_saved(self):
        started = time.monotonic()
        self.launch()
        self.assertLess(time.monotonic() - started, .5)
        self.assertEqual(self.card.list(), [])
        self.assertTrue(self.job.wait(30))
        state = self.job.snapshot()
        self.assertEqual(state['phase'], 'saved')
        self.assertEqual(state['worker_exit_code'], 0)
        self.assertFalse(state['worker_running'])
        self.assertEqual(state['result']['name'], 'Z62_0001.MP4')
        self.assertEqual(self.card.full_item('Z62_0001.MP4')['metadata']['duration_us'], 90000)

    def test_cancel_a_confirmed_live_worker_is_responsive_and_publishes_nothing(self):
        worker, environment = self.fault('block')
        with worker, environment:
            self.launch()
            state = self.wait(lambda s: s['worker_running'] and (self.job.work / 'fixture-entered').exists())
            self.assertIsInstance(state['worker_pid'], int)
            started = time.monotonic()
            self.assertEqual(self.card.summary()['videos'], 0)
            self.job.cancel()
            self.assertLess(time.monotonic() - started, .5)
            self.assertTrue(self.job.wait(15))
        self.assertEqual(self.job.snapshot()['phase'], 'cancelled')
        self.assertFalse(self.job.snapshot()['worker_running'])
        self.assertEqual(self.card.list(), [])

    def test_ready_file_is_not_completion_while_its_worker_is_still_alive(self):
        worker, environment = self.fault('ready-but-live')
        with worker, environment:
            self.launch()
            self.wait(lambda s: s['worker_running'] and (self.job.work / 'fixture-entered').exists(), 30)
            self.assertTrue((self.job.work / 'result.json').exists())
            self.assertEqual(self.card.list(), [])
            self.assertNotEqual(self.job.snapshot()['phase'], 'saved')
            self.job.cancel()
            self.assertTrue(self.job.wait(15))
        self.assertEqual(self.card.list(), [])

    def test_worker_reported_error_is_not_terminal_until_the_live_process_stops(self):
        worker, environment = self.fault('error-but-live')
        with worker, environment:
            self.launch()
            self.wait(lambda s: s['worker_running'] and (self.job.work / 'fixture-entered').exists())
            time.sleep(.1)
            try:
                self.assertTrue(self.job.cancel())
            finally:
                # Ensure the intentionally faulty API cannot leak this test's worker.
                self.job.cancelled.set()
                self.assertTrue(self.job.wait(15))
        self.assertEqual(self.card.list(), [])

    def test_containment_assignment_failure_terminates_the_owned_waiting_process_promptly(self):
        with patch.object(self.api.WorkerContainment, 'assign', side_effect=OSError('assignment failed')):
            self.launch()
            try:
                self.assertTrue(self.job.wait(3), 'An unassigned worker must be terminated by its owned process handle')
            finally:
                if self.job.process is not None and self.job.process.poll() is None:
                    self.job.process.terminate()
                self.assertTrue(self.job.wait(15))
        self.assertEqual(self.job.snapshot()['phase'], 'error')
        self.assertEqual(self.card.list(), [])

    @unittest.skipUnless(os.name == 'nt', 'Windows Job Object descendant containment')
    def test_cancel_stops_a_confirmed_live_descendant_by_job_handle(self):
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        worker, environment = self.fault('descendant')
        with worker, environment:
            self.launch()
            self.wait(lambda s: s['worker_running'] and (self.job.work / 'fixture-entered').exists())
            pid = int((self.job.work / 'descendant.pid').read_text(encoding='ascii'))
            handle = kernel.OpenProcess(0x101000, False, pid)
            self.assertTrue(handle)
            try:
                self.assertEqual(kernel.WaitForSingleObject(handle, 0), 258)  # WAIT_TIMEOUT: still alive
                self.job.cancel()
                self.assertTrue(self.job.wait(15))
                self.assertEqual(kernel.WaitForSingleObject(handle, 5000), 0)  # signalled process handle
            finally:
                kernel.CloseHandle(handle)
        self.assertEqual(self.job.snapshot()['phase'], 'cancelled')
        self.assertEqual(self.card.list(), [])

    def test_nonzero_exit_rejects_even_a_valid_result_file(self):
        worker, environment = self.fault('exit-nonzero')
        with worker, environment:
            self.launch()
            self.assertTrue(self.job.wait(30))
        self.assertEqual(self.job.snapshot()['phase'], 'error')
        self.assertEqual(self.job.snapshot()['worker_exit_code'], 7)
        self.assertEqual(self.card.list(), [])

    def test_wrong_source_and_changed_movie_are_not_published(self):
        for mode in ('corrupt-source', 'corrupt-file'):
            with self.subTest(mode=mode):
                recorder = VideoRecorder(self.root, start_ns=0, clock_epoch='video-test')
                self.addCleanup(recorder.abort)
                recorder.append(frame('red', 10_000_000, 1))
                recorder.append(frame('blue', 70_000_000, 2))
                worker, environment = self.fault(mode)
                with worker, environment:
                    job = self.api.VideoJob(recorder, self.card, self.root / 'jobs', stop_ns=100_000_000)
                    self.addCleanup(lambda job=job: job.close(timeout=15))
                    job.start()
                    self.assertTrue(job.wait(30))
                self.assertEqual(job.snapshot()['phase'], 'error')
                self.assertEqual(self.card.list(), [])

    def test_deadline_terminates_the_owned_worker_without_a_movie(self):
        worker, environment = self.fault('block')
        with worker, environment:
            self.launch(timeout_s=.6)
            self.assertTrue(self.job.wait(15))
        state = self.job.snapshot()
        self.assertEqual(state['phase'], 'error')
        self.assertIn('timeout', state['error']['message'])
        self.assertFalse(state['worker_running'])
        self.assertEqual(self.card.list(), [])

    def test_card_full_is_an_error_after_validation_not_a_saved_movie(self):
        self.card.close()
        self.card = AsyncVideoCard.create(self.root / 'small', capacity_bytes=1)
        self.addCleanup(self.card.close)
        self.launch()
        self.assertTrue(self.job.wait(30))
        self.assertEqual(self.job.snapshot()['phase'], 'error')
        self.assertIn('card_full', self.job.snapshot()['error']['message'])
        self.assertEqual(self.card.list(), [])

    def test_cancellation_cannot_claim_to_undo_a_commit_that_has_started(self):
        entered, release = threading.Event(), threading.Event()
        publish = self.card._publish_media

        def gated(*args):
            entered.set()
            if not release.wait(8):
                raise RuntimeError('commit test gate expired')
            return publish(*args)

        with patch.object(self.card, '_publish_media', gated):
            self.launch()
            try:
                self.assertTrue(entered.wait(30))
                self.assertEqual(self.job.snapshot()['phase'], 'committing')
                with self.assertRaisesRegex(ValueError, 'commit'):
                    self.job.cancel()
            finally:
                release.set()
                self.assertTrue(self.job.wait(15))
        self.assertEqual(self.job.snapshot()['phase'], 'saved')
        self.assertEqual(len(self.card.list()), 1)


if __name__ == '__main__':
    unittest.main()
