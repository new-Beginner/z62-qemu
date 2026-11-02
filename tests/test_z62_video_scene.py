"""Actual recording lifecycle, source pump and observable failure states."""
from importlib.util import find_spec
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from z62_video_card import VideoCard
from test_z62_video_codec import frame


@unittest.skipUnless(find_spec('av'), 'Optional video profile: use .build/tools/video-r26/Scripts/python.exe')
class VideoSceneTests(unittest.TestCase):
    def setUp(self):
        try:
            from z62_video_scene import VideoSceneCamera
        except ImportError as exc:
            self.fail('The video camera lifecycle is missing: ' + str(exc))
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.card = VideoCard.create(Path(self.temp.name) / 'card')
        self.addCleanup(self.card.close)
        self.camera = VideoSceneCamera(card=self.card, video_directory=Path(self.temp.name),
                                       width=64, height=64, clock_epoch='video-test')
        self.addCleanup(self.camera.abort_video)
        self.current = frame('red', 10_000_000, 1)
        self.camera.native_frame_provider = lambda ns: self.current
        self.camera.event('power', {'on': True}, 0)
        self.camera.event('mode', {'mode': 'video'}, 0)

    def start(self):
        self.camera.event('record', {'action': 'start'}, 5_000_000)

    def feed(self):
        self.camera.observe_video(20_000_000)
        self.current = frame('blue', 70_000_000, 2)
        self.camera.observe_video(80_000_000)

    def test_start_acquire_stop_save_replay_and_delete_a_real_movie(self):
        self.start()
        self.feed()
        result = self.camera.event('record', {'action': 'stop'}, 100_000_000)['result']
        self.assertEqual(result['name'], 'Z62_0001.MP4')
        self.assertEqual(self.camera.status(100_000_000)['video']['phase'], 'saved')
        self.camera.event('playback', {'action': 'open'}, 100_000_000)
        displayed = self.camera.display(100_000_000)
        self.assertGreater(displayed.image.getpixel((20, 20))[0], 240)
        self.camera.event('delete', {}, 100_000_000)
        self.assertEqual(self.card.list(), [])

    def test_duplicate_start_stop_and_mode_changes_do_not_duplicate_or_discard_a_clip(self):
        self.start()
        for kind, payload in (('record', {'action': 'start'}), ('mode', {'mode': 'photo'}),
                              ('power', {'on': False}), ('playback', {'action': 'open'})):
            with self.assertRaises(ValueError):
                self.camera.event(kind, payload, 5_000_000)
        self.feed()
        self.camera.event('record', {'action': 'stop'}, 100_000_000)
        with self.assertRaises(ValueError):
            self.camera.event('record', {'action': 'stop'}, 100_000_000)
        self.assertEqual(len(self.card.list()), 1)

    def test_recording_requires_a_card_and_video_mode(self):
        self.camera.card = None
        with self.assertRaisesRegex(ValueError, 'no_card'):
            self.start()
        self.camera.card = self.card
        self.camera.event('mode', {'mode': 'photo'}, 5_000_000)
        with self.assertRaisesRegex(ValueError, 'video_mode'):
            self.start()
        self.assertEqual(self.camera.status(5_000_000)['video']['phase'], 'idle')

    def test_card_full_at_stop_keeps_no_visible_clip(self):
        small = VideoCard.create(Path(self.temp.name) / 'small', capacity_bytes=1)
        self.addCleanup(small.close)
        self.camera.card = small
        self.start()
        self.feed()
        with self.assertRaisesRegex(ValueError, 'card_full'):
            self.camera.event('record', {'action': 'stop'}, 100_000_000)
        self.assertEqual(self.camera.status(100_000_000)['video']['phase'], 'error')
        self.assertEqual(small.list(), [])

    def test_bad_source_aborts_recording_without_a_fake_movie(self):
        self.start()
        self.current.metadata['pixel_sha256'] = '0' * 64
        self.camera.observe_video(20_000_000)
        state = self.camera.status(20_000_000)['video']
        self.assertEqual(state['phase'], 'error')
        self.assertFalse(state['recording'])
        self.assertEqual(self.card.list(), [])

    def test_repeated_publications_and_cancel_do_not_publish_a_movie(self):
        self.start()
        self.camera.observe_video(20_000_000)
        self.camera.observe_video(21_000_000)
        self.assertEqual(self.camera.status(21_000_000)['video']['frames'], 1)
        self.camera.event('record', {'action': 'cancel'}, 22_000_000)
        self.assertEqual(self.card.list(), [])
        self.assertFalse(self.camera.status(22_000_000)['video']['recording'])

    def test_stop_at_a_source_boundary_reports_the_actual_encoded_frame_count(self):
        self.start()
        self.feed()
        self.current = frame('green', 110_000_000, 3)
        self.camera.observe_video(110_000_000)
        try:
            self.camera.event('record', {'action': 'stop'}, 110_000_000)
        except ValueError as exc:
            self.fail('A stop coincident with a source observation must finish the earlier frames: ' + str(exc))
        self.assertEqual(self.camera.status(110_000_000)['video']['frames'], 2)
        self.assertEqual(len(self.card.list()[0]['metadata']['samples']), 2)


if __name__ == '__main__':
    unittest.main()
