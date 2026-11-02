"""One issued body edge drives the explicit C photo model exactly once."""
from pathlib import Path
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from z62_directory_card import DirectoryCard
from z62_software_camera import SoftwareCamera


class UnifiedInputTests(unittest.TestCase):
    def setUp(self):
        try:
            from z62_unified_camera_input import UnifiedCameraInputMixin
        except ImportError as exc:
            self.fail('The shared body/scene event adapter is missing: ' + str(exc))
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.card = DirectoryCard.create(Path(temp.name) / 'card')
        self.addCleanup(self.card.close)
        self.camera = SoftwareCamera(card=self.card, width=160, height=104)
        self.camera.event('power', {'on': True}, 0)
        camera = self.camera

        class Base:
            def __init__(self):
                self.io = threading.Lock()
                self.phase = 'running'
                self.physical = []
                self.fail_physical = False

            def _drive_key_pin(self, pin, level):
                if self.fail_physical:
                    raise TimeoutError('physical result unknown')
                self.physical.append((pin, level))

            def _software_locked(self):
                return camera, 0

            def status(self):
                return {'phase': self.phase}

        class Host(UnifiedCameraInputMixin, Base):
            pass

        self.host = Host()

    def edge(self, pin, level):
        with self.host.io:
            self.host._drive_key_pin(pin, level)

    def click(self, pin):
        self.edge(pin, 0)
        self.edge(pin, 1)

    def test_full_press_is_captured_only_after_the_physical_edge(self):
        self.edge(25, 0)
        self.edge(25, 0)
        self.assertEqual(len(self.card.list()), 1)
        self.assertEqual(self.host.physical, [(25, 0), (25, 0)])
        self.assertEqual(self.host.camera_input_status()['last_event']['hardware_outcome'], 'issued')
        self.edge(25, 1)
        self.click(25)
        self.assertEqual(len(self.card.list()), 2)

    def test_unknown_physical_result_never_generates_a_software_photo(self):
        self.host.fail_physical = True
        with self.assertRaises(TimeoutError):
            self.edge(25, 0)
        self.assertEqual(self.card.list(), [])
        last = self.host.camera_input_status()['last_event']
        self.assertEqual(last['hardware_outcome'], 'unknown')
        self.assertFalse(last['software_applied'])

    def test_photo_storage_error_does_not_forge_success_or_fail_the_input_worker(self):
        self.camera.card = None
        self.edge(25, 0)
        last = self.host.camera_input_status()['last_event']
        self.assertEqual(self.host.physical, [(25, 0)])
        self.assertEqual(self.host.phase, 'running')
        self.assertFalse(last['software_applied'])
        self.assertIn('no_card', last['error'])
        self.edge(25, 1)
        self.assertFalse(self.camera.status(0)['full_pressed'])

    def test_play_zoom_and_delete_share_the_body_edge_path(self):
        self.click(25)
        self.click(8)
        self.assertEqual(self.camera.status(0)['view'], 'playback')
        self.click(22)
        self.assertEqual(self.camera.status(0)['zoom'], 2)
        self.click(21)
        self.assertEqual(self.camera.status(0)['zoom'], 1)
        self.click(23)
        self.assertEqual(self.card.list(), [])
        self.assertEqual(self.camera.status(0)['view'], 'live')

    def test_af_and_record_inputs_do_not_fabricate_algorithm_results(self):
        self.click(26)
        self.click(29)
        self.assertEqual(self.card.list(), [])
        self.assertFalse(self.camera.status(0)['capabilities']['factory_af'])
        self.assertFalse(self.camera.status(0)['lens']['moving'])


if __name__ == '__main__':
    unittest.main()
