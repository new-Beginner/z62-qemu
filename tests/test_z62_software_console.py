"""The opt-in host must use the guest clock and preserve file ownership."""
from io import BytesIO
from pathlib import Path
import sys
import tempfile
import threading
import unittest

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))


class SoftwareConsoleTests(unittest.TestCase):
    def setUp(self):
        try:
            from z62_software_console import SoftwareCameraMixin
        except ImportError as exc:
            self.fail('The opt-in QEMU software-camera adapter is missing: ' + str(exc))
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)

        class Base:
            def __init__(self):
                self.io = threading.Lock()
                self.phase = 'running'
                self.work = root / 'epoch-1'
                self.ticks = 0

            def _ready(self):
                if self.phase != 'running':
                    raise RuntimeError('not running')

            def _key_clock(self):
                if self.ticks is None:
                    raise TimeoutError('clock observation unavailable')
                return self.ticks, 1000

            def status(self):
                return {'phase': self.phase}

            def close(self):
                self.phase = 'stopped'

        class Host(SoftwareCameraMixin, Base):
            software_config = {'card': str(root / 'card'), 'width': 160, 'height': 104, 'scene': None}

        self.host = Host()
        self.addCleanup(self.host.close)

    def test_capture_uses_guest_clock_and_jpeg_is_available_through_the_adapter(self):
        h = self.host
        h.software_event({'type': 'power', 'payload': {'on': True}})
        h.ticks = 1000
        result = h.software_event({'type': 'shutter', 'payload': {'stage': 'full', 'pressed': True}})
        self.assertEqual(result['result']['metadata']['virtual_time_ns'], 1_000_000_000)
        self.assertEqual(result['result']['metadata']['frame_id'], 30)
        h.software_event({'type': 'playback', 'payload': {'action': 'open'}})
        with Image.open(BytesIO(h.software_frame())) as image:
            image.load()
            self.assertEqual(image.size, (160, 104))

    def test_missing_clock_cannot_generate_a_photo_or_advance_the_scene(self):
        h = self.host
        h.software_event({'type': 'power', 'payload': {'on': True}})
        h.ticks = None
        with self.assertRaises(TimeoutError):
            h.software_event({'type': 'shutter', 'payload': {'stage': 'full', 'pressed': True}})
        h.ticks = 0
        self.assertEqual(h.software_status()['card']['images'], [])
        self.assertEqual(h.software_status()['virtual_time_ns'], 0)

    def test_new_vm_epoch_resets_model_time_but_keeps_committed_photos(self):
        h = self.host
        h.software_event({'type': 'power', 'payload': {'on': True}})
        h.ticks = 1000
        first = h.software_event({'type': 'shutter', 'payload': {'stage': 'full', 'pressed': True}})
        h.work = h.work.parent / 'epoch-2'
        h.ticks = 0
        state = h.software_status()
        self.assertFalse(state['powered'])
        self.assertEqual(state['virtual_time_ns'], 0)
        self.assertEqual(len(state['card']['images']), 1)
        self.assertNotEqual(state['clock_epoch'], first['result']['metadata']['clock_epoch'])

    def test_close_releases_the_owned_card_lease(self):
        import z62_directory_card as storage
        self.host.software_status()
        self.host.close()
        with storage.DirectoryCard(self.host.software_config['card']) as card:
            self.assertEqual(card.list(), [])


if __name__ == '__main__':
    unittest.main()
