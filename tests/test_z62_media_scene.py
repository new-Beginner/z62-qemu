"""Live consumed-source captures publish real grouped NEF/JPEG media."""
import hashlib
from io import BytesIO
from pathlib import Path
import sys
import tempfile
import unittest

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from z62_media_card import MediaCard
from z62_scene_packet import make_packet
from z62_software_camera import Frame
from z62_nef_codec import inspect_nef, raw14_from_consumed_frame


class MediaSceneTests(unittest.TestCase):
    def setUp(self):
        try:
            from z62_media_scene import MediaSceneCamera
        except ImportError as exc:
            self.fail('The camera NEF integration is missing: ' + str(exc))
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.card = MediaCard.create(Path(temp.name) / 'card')
        self.addCleanup(self.card.close)
        self.camera = MediaSceneCamera(card=self.card, width=160, height=104)
        self.camera.event('power', {'on': True}, 0)
        image = Image.new('RGB', (160, 104), 'white')
        packet = make_packet(image, epoch=62, publish_id=7, frame_id=3, virtual_time_ns=100_000_000)
        self.frame = Frame(image, {'implementation_level': 'C', 'frame_id': 3, 'virtual_time_ns': 100_000_000,
            'width': 160, 'height': 104, 'pixel_sha256': hashlib.sha256(image.tobytes()).hexdigest(),
            'native_scene_source': {'epoch': 62, 'publish_id': 7, 'frame_id': 3,
                                    'virtual_time_ns': 100_000_000, 'raw_sha256': packet[56:88].hex()},
            'exposure': {'iso': 100, 'shutter_seconds': .008}, 'lens': {'aperture': 4, 'focal_length_mm': 50}})
        self.camera.native_frame_provider = lambda now: self.frame

    def test_one_shutter_publishes_a_pair_from_the_acknowledged_native_frame(self):
        result = self.camera.event('shutter', {'stage': 'full', 'pressed': True}, 120_000_000)['result']
        self.assertEqual(len(self.card.list()), 1)
        self.assertEqual([row['name'] for row in result['files']], ['Z62_0001.JPG', 'Z62_0001.NEF'])
        info = inspect_nef(self.card.read('Z62_0001.NEF'))
        self.assertEqual((info['width'], info['height']), (1514, 1006))
        self.assertEqual(info['description']['native_scene_source']['publish_id'], 7)
        self.assertEqual(info['description']['raw_effective_source_bits'], 12)
        self.assertEqual(info['description']['raw_storage_bits'], 14)

    def test_nef_only_replays_its_actual_embedded_preview_and_deletes(self):
        self.camera.capture_format = 'nef'
        self.camera.event('shutter', {'stage': 'full', 'pressed': True}, 120_000_000)
        self.camera.event('playback', {'action': 'open'}, 120_000_000)
        self.assertEqual(self.camera.playback, 'Z62_0001.NEF')
        displayed = self.camera.display(120_000_000)
        self.assertEqual(displayed.image.size, (160, 104))
        self.assertGreater(displayed.image.getpixel((80, 52))[0], 240)
        self.camera.event('delete', {}, 120_000_000)
        self.assertEqual(self.card.list(), [])

    def test_bad_native_source_identity_cannot_be_saved_as_nef(self):
        self.frame.metadata['native_scene_source']['raw_sha256'] = '0' * 64
        with self.assertRaises(ValueError):
            self.camera.event('shutter', {'stage': 'full', 'pressed': True}, 120_000_000)
        self.assertEqual(self.card.list(), [])

    def test_raw_precision_and_levels_preserve_the_consumed_twelve_bit_source(self):
        for color, expected in (('black', 256), ('white', 16380)):
            with self.subTest(color=color):
                image = Image.new('RGB', (160, 104), color)
                packet = make_packet(image, epoch=62, publish_id=7, frame_id=3, virtual_time_ns=100_000_000)
                self.frame.image = image
                self.frame.metadata['pixel_sha256'] = hashlib.sha256(image.tobytes()).hexdigest()
                self.frame.metadata['native_scene_source']['raw_sha256'] = packet[56:88].hex()
                raw, metadata = raw14_from_consumed_frame(self.frame)
                self.assertEqual(raw.shape, (1006, 1514))
                self.assertTrue((raw == expected).all())
                self.assertEqual(metadata['raw_effective_source_bits'], 12)
                self.assertEqual(metadata['raw_storage_bits'], 14)
                self.assertNotIn('raw14_sha256', self.frame.metadata)

    def test_changed_pixels_or_mismatched_frame_tags_cannot_publish_a_photo(self):
        for corruption in ('pixels', 'frame_id', 'virtual_time_ns'):
            with self.subTest(corruption=corruption):
                if corruption == 'pixels':
                    self.frame.image.putpixel((0, 0), (0, 0, 0))
                else:
                    self.frame.metadata[corruption] += 1
                with self.assertRaises(ValueError):
                    raw14_from_consumed_frame(self.frame)
                self.assertEqual(self.card.list(), [])
                if corruption == 'pixels':
                    self.frame.image.putpixel((0, 0), (255, 255, 255))
                else:
                    self.frame.metadata[corruption] -= 1


if __name__ == '__main__':
    unittest.main()
