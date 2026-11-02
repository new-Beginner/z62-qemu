"""Stopping must not block guest-state access; completion never rewinds its clock."""
from importlib.util import find_spec
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from z62_async_video_card import AsyncVideoCard
import z62_async_video_job as jobs
from test_z62_video_codec import frame

FIXTURE = Path(__file__).with_name('helpers') / 'video_worker_fixture.py'


@unittest.skipUnless(find_spec('av'), 'Optional video profile requires the isolated video Python')
class AsyncVideoSceneTests(unittest.TestCase):
    def setUp(self):
        try:
            from z62_async_video_scene import AsyncVideoSceneCamera
        except ImportError as exc:
            self.fail('The asynchronous video camera is missing: ' + str(exc))
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        (self.root / 'jobs').mkdir()
        self.card = AsyncVideoCard.create(self.root / 'card')
        self.addCleanup(self.card.close)
        self.camera = AsyncVideoSceneCamera(card=self.card, video_directory=self.root,
            job_directory=self.root / 'jobs', width=64, height=64, clock_epoch='video-test')
        self.addCleanup(lambda: self.camera.close_video(timeout=15))
        self.current = frame('red', 10_000_000, 1)
        self.camera.native_frame_provider = lambda now: self.current
        self.camera.event('power', {'on': True}, 0)
        self.camera.event('mode', {'mode': 'video'}, 0)

    def prepare(self):
        self.camera.event('record', {'action': 'start'}, 5_000_000)
        self.camera.observe_video(20_000_000)
        self.current = frame('blue', 70_000_000, 2)
        self.camera.observe_video(80_000_000)

    def wait_live(self):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            state = self.camera.status(self.camera.time_ns)['video']
            if state.get('worker_running') and Path(state['job_directory'], 'fixture-entered').exists():
                return state
            time.sleep(.02)
        self.fail('Expected a confirmed live worker')

    def test_stop_returns_quickly_and_status_lens_and_guest_time_continue(self):
        with patch.object(jobs, 'WORKER_SCRIPT', FIXTURE), patch.dict('os.environ', {'Z62_ASYNC_TEST_MODE': 'block'}):
            self.prepare()
            started = time.monotonic()
            response = self.camera.event('record', {'action': 'stop'}, 100_000_000)
            self.assertLess(time.monotonic() - started, .5)
            self.assertTrue(response['result']['encoding'])
            self.wait_live()
            started = time.monotonic()
            self.camera.event('exposure', {'iso': 400}, 120_000_000)
            self.camera.event('lens', {'focus_target': .65}, 130_000_000)
            self.camera.observe_video(140_000_000)
            state = self.camera.status(150_000_000)
            self.assertLess(time.monotonic() - started, .5)
            self.assertEqual(state['virtual_time_ns'], 150_000_000)
            self.assertEqual(state['video']['frames'], 2)
            self.assertFalse(state['video']['recording'])
            self.assertNotEqual(state['video']['phase'], 'saved')
            self.assertEqual(state['card']['videos'], 0)

    def test_background_completion_preserves_stop_time_and_current_guest_clock(self):
        self.prepare()
        self.camera.event('record', {'action': 'stop'}, 100_000_000)
        self.camera.status(150_000_000)
        self.assertTrue(self.camera.wait_video(30))
        state = self.camera.status(200_000_000)
        self.assertEqual(state['video']['phase'], 'saved')
        self.assertEqual(state['virtual_time_ns'], 200_000_000)
        detail = self.card.full_item('Z62_0001.MP4')
        self.assertEqual(detail['metadata']['stop_request_ns'], 100_000_000)
        self.assertEqual(detail['metadata']['duration_us'], 90000)

    def test_encoding_cancel_is_nonblocking_and_never_publishes(self):
        with patch.object(jobs, 'WORKER_SCRIPT', FIXTURE), patch.dict('os.environ', {'Z62_ASYNC_TEST_MODE': 'block'}):
            self.prepare()
            self.camera.event('record', {'action': 'stop'}, 100_000_000)
            self.wait_live()
            started = time.monotonic()
            result = self.camera.event('record', {'action': 'cancel'}, 110_000_000)
            self.assertLess(time.monotonic() - started, .5)
            self.assertTrue(result['result']['cancel_requested'])
            self.assertTrue(self.camera.wait_video(15))
        self.assertEqual(self.camera.status(120_000_000)['video']['phase'], 'cancelled')
        self.assertEqual(self.card.list(), [])

    def test_shutdown_waits_for_actual_worker_exit_before_card_can_close(self):
        with patch.object(jobs, 'WORKER_SCRIPT', FIXTURE), patch.dict('os.environ', {'Z62_ASYNC_TEST_MODE': 'block'}):
            self.prepare()
            self.camera.event('record', {'action': 'stop'}, 100_000_000)
            self.wait_live()
            self.camera.close_video(timeout=15)
        state = self.camera.status(110_000_000)['video']
        self.assertTrue(state['terminal'])
        self.assertFalse(state['worker_running'])
        self.card.close()
        with AsyncVideoCard(self.root / 'card') as reopened:
            self.assertEqual(reopened.list(), [])

    def test_second_record_request_is_rejected_until_the_active_job_is_terminal(self):
        with patch.object(jobs, 'WORKER_SCRIPT', FIXTURE), patch.dict('os.environ', {'Z62_ASYNC_TEST_MODE': 'block'}):
            self.prepare()
            self.camera.event('record', {'action': 'stop'}, 100_000_000)
            self.wait_live()
            for action in ('start', 'stop'):
                with self.assertRaisesRegex(ValueError, 'job_active'):
                    self.camera.event('record', {'action': action}, 110_000_000)

    def test_background_write_failure_is_visible_without_a_saved_receipt(self):
        self.prepare()
        with patch.object(self.card, '_publish_media', side_effect=OSError('asynchronous write failed')):
            self.camera.event('record', {'action': 'stop'}, 100_000_000)
            self.assertTrue(self.camera.wait_video(30))
        state = self.camera.status(120_000_000)['video']
        self.assertEqual(state['phase'], 'error')
        self.assertIsNone(state['result'])
        self.assertIn('write failed', state['error']['message'])
        self.assertEqual(self.card.list(), [])


if __name__ == '__main__':
    unittest.main()
