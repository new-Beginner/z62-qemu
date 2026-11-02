"""Record toggles follow successfully issued GPIO edges, not HTTP intentions."""
from importlib.util import find_spec
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from z62_video_card import VideoCard
from z62_video_scene import VideoSceneCamera
from z62_unified_camera_input import UnifiedCameraInputMixin
from test_z62_video_codec import frame


@unittest.skipUnless(find_spec('av'), 'Optional video profile: use .build/tools/video-r26/Scripts/python.exe')
class VideoInputTests(unittest.TestCase):
    def setUp(self):
        try:
            from z62_video_input import VideoBodyInputMixin
        except ImportError as exc:
            self.fail('The shared video body-edge adapter is missing: ' + str(exc))
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.card = VideoCard.create(Path(temp.name) / 'card')
        self.addCleanup(self.card.close)
        camera = self.camera = VideoSceneCamera(card=self.card, video_directory=Path(temp.name),
                                                width=64, height=64, clock_epoch='video-test')
        self.addCleanup(camera.abort_video)
        camera.event('power', {'on': True}, 0)
        camera.event('mode', {'mode': 'video'}, 0)
        self.current = frame('red', 10_000_000, 1)
        camera.native_frame_provider = lambda now: self.current

        class Base:
            def __init__(self):
                self.io = threading.Lock()
                self.work = 'test-epoch'
                self.now = 0
                self.physical = []
                self.fail_physical = False

            def _drive_key_pin(self, pin, level):
                if self.fail_physical:
                    raise TimeoutError('GPIO outcome unknown')
                self.physical.append((pin, level))

            def _software_locked(self):
                return camera, self.now

            def _release(self):
                self.physical.append((29, 1))

        class Host(VideoBodyInputMixin, UnifiedCameraInputMixin, Base):
            pass

        self.host = Host()

    def edge(self, level):
        with self.host.io:
            self.host._drive_key_pin(29, level)

    def feed(self):
        self.camera.observe_video(20_000_000)
        self.current = frame('blue', 70_000_000, 2)
        self.camera.observe_video(80_000_000)
        self.host.now = 100_000_000

    def test_one_press_starts_and_next_press_saves_once(self):
        self.edge(0)
        self.edge(0)
        self.assertTrue(self.camera.status(0)['video']['recording'])
        self.assertEqual(self.card.list(), [])
        self.feed()
        self.edge(1)
        self.edge(0)
        self.assertEqual([row['name'] for row in self.card.list()], ['Z62_0001.MP4'])
        event = self.host.camera_input_status()['last_event']
        self.assertTrue(event['software_applied'])
        self.assertEqual(event['hardware_outcome'], 'issued')
        self.assertEqual(self.host.physical, [(29, 0), (29, 0), (29, 1), (29, 0)])

    def test_unknown_gpio_does_not_start_or_replay_a_recording(self):
        self.host._video_pending_action = 'start'
        self.host.fail_physical = True
        with self.assertRaises(TimeoutError):
            self.edge(0)
        self.assertIsNone(self.host._video_pending_action)
        self.assertFalse(self.camera.status(0)['video']['recording'])
        self.assertEqual(self.host.camera_input_status()['last_event']['hardware_outcome'], 'unknown')

    def test_video_storage_error_does_not_escape_the_firmware_input_worker(self):
        self.edge(0)
        self.feed()
        self.edge(1)
        with patch.object(self.card, 'store_video', side_effect=OSError('simulated write failure')):
            self.edge(0)
        self.assertEqual(self.card.list(), [])
        self.assertEqual(self.camera.status(self.host.now)['video']['phase'], 'error')
        self.assertIn('write failure', self.host.camera_input_status()['last_event']['error'])

    def test_release_all_rearms_record_key_without_ending_the_recording(self):
        self.edge(0)
        self.feed()
        self.host._release()
        self.assertTrue(self.camera.status(self.host.now)['video']['recording'])
        self.edge(0)
        self.assertEqual(len(self.card.list()), 1)


if __name__ == '__main__':
    unittest.main()
