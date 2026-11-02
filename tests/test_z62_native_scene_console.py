"""A native-profile JPEG must use the acknowledged input, not a newer render."""
from io import BytesIO
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from z62_directory_card import DirectoryCard
from z62_software_camera import CameraError, Frame


class NativeSceneCameraTests(unittest.TestCase):
    def setUp(self):
        try:
            from z62_native_scene_console import NativeSceneCamera
        except ImportError as exc:
            self.fail('The consumed-frame camera integration is missing: ' + str(exc))
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.card = DirectoryCard.create(Path(temp.name) / 'card')
        self.addCleanup(self.card.close)
        self.camera = NativeSceneCamera(card=self.card, width=160, height=104)
        self.camera.event('power', {'on': True}, 0)

    def test_photo_and_display_use_the_consumed_frame_identity(self):
        frame = Frame(Image.new('RGB', (160, 104), (255, 0, 0)), {
            'implementation_level': 'C', 'width': 160, 'height': 104,
            'frame_id': 3, 'virtual_time_ns': 100_000_000,
            'native_scene_source': {'publish_id': 7, 'epoch': 0x62}})
        self.camera.native_frame_provider = lambda now: frame
        saved = self.camera.event('shutter', {'stage': 'full', 'pressed': True}, 120_000_000)['result']
        with Image.open(BytesIO(self.card.read(saved['name']))) as image:
            metadata = json.loads(image.getexif()[270])
            self.assertEqual(metadata['native_scene_source']['publish_id'], 7)
            self.assertEqual(metadata['frame_id'], 3)
            self.assertGreater(image.getpixel((80, 52))[0], 240)
            self.assertLess(image.getpixel((80, 52))[1], 10)
        self.assertEqual(self.camera.display(120_000_000).image.getpixel((0, 0)), (255, 0, 0))
        # Source generation must still render the current scene, not recurse into display.
        self.assertFalse(self.camera.frame(120_000_000).image.tobytes() == frame.image.tobytes())

    def test_unacknowledged_input_never_becomes_a_photo(self):
        def pending(now):
            raise CameraError('scene_settings_pending')
        self.camera.native_frame_provider = pending
        with self.assertRaisesRegex(CameraError, 'scene_settings_pending'):
            self.camera.event('shutter', {'stage': 'full', 'pressed': True}, 0)
        self.assertEqual(self.card.list(), [])

    def test_native_profile_installs_before_outer_capture_status_injection(self):
        import shutil
        import z62_shutter_input_v2 as shutter
        import z62_capture_input as capture
        import z62_body_controls as body
        import z62_encoder_queue as encoder
        import z62_encoder_labels as labels
        import z62_extra_console as extra
        import z62_mode_console as mode
        import z62_software_console as software
        import z62_native_scene_console as native
        from z62_scene_packet import parse_packet
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as folder:
            stage = Path(folder)
            for name in ('tools/z62_console.py', 'web-z62/index.html', 'web-z62/console.js', 'web-z62/style.css'):
                target = stage / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(root / 'third_party/z62-qemu' / name, target)
            for adapter in (shutter, capture, body, encoder, labels, extra, mode):
                adapter.apply_console(stage)
            config = {'card': None, 'scene': None, 'width': 160, 'height': 104}
            software.apply_console(stage, config)
            native.apply_console(stage, config)
            compile((stage / 'tools/z62_console.py').read_text(encoding='utf-8'), 'staged-profile', 'exec')
            info, raw = parse_packet((stage / 'native-initial.scene').read_bytes())
            self.assertEqual((info['publish_id'], info['frame_id']), (1, 0))
            self.assertEqual(len(raw), 2_285_632)

    def test_queued_edge_response_uses_the_later_observed_callback_time(self):
        from z62_native_scene_console import NativeSceneMixin
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as folder:
            work = Path(folder) / 'run'
            work.mkdir()
            def command(name, args):
                return 0 if args['property'] == 'scene-used-publish-id' else 1 if name == 'qom-get' else None
            class Base:
                def __init__(self):
                    self.work = work
                    self.io = threading.Lock()
                    self.phase = 'running'
                    self.qmp = SimpleNamespace(command=command)
                    self.ticks = 0
                    self.key_events = {}
                def _ready(self):
                    pass
                def _key_clock(self):
                    self.ticks += 10
                    return self.ticks, 1000
                def _drive_key_pin(self, pin, level):
                    pass
                def _set_key_locked(self, pin, level):
                    self._drive_key_pin(pin, level)
            class Host(NativeSceneMixin, Base):
                software_config = {'card': None, 'scene': None, 'width': 160, 'height': 104, 'auto_scene_pump': False}
            result = Host().software_event({'type': 'shutter', 'payload': {'stage': 'half', 'pressed': True}})
            self.assertTrue(result['state']['half_pressed'])
            self.assertEqual(result['state']['virtual_time_ns'], 20_000_000)


if __name__ == '__main__':
    unittest.main()
