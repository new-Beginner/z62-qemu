"""Pixel, virtual-time and persisted-file contracts for the explicit C backend."""
import hashlib
from io import BytesIO
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
import unittest

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))


class SoftwareCameraTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        # Import here so a missing backend is reported as the missing feature.
        try:
            import z62_software_camera as camera
            import z62_directory_card as storage
        except ImportError as exc:
            self.fail('The software camera and owned-card backend are missing: ' + str(exc))
        self.api, self.storage = camera, storage
        self.card = storage.DirectoryCard.create(self.root / 'card', capacity_bytes=2_000_000)
        self.addCleanup(self.card.close)
        self.camera = camera.SoftwareCamera(card=self.card, width=160, height=104)
        self.camera.event('power', {'on': True}, 0)

    def capture(self, time_ns=1_000_000_000):
        result = self.camera.event('shutter', {'stage': 'full', 'pressed': True}, time_ns)
        self.camera.event('shutter', {'stage': 'full', 'pressed': False}, time_ns)
        return result['result']

    def test_same_frame_and_initial_state_are_reproducible(self):
        first = self.camera.frame(123_000_000)
        second = self.camera.frame(123_000_000)
        self.assertEqual(first.metadata['frame_id'], 3)
        self.assertEqual(first.metadata['virtual_time_ns'], 123_000_000)
        self.assertEqual(first.image.tobytes(), second.image.tobytes())
        other = self.api.SoftwareCamera(width=160, height=104)
        other.event('power', {'on': True}, 0)
        self.assertEqual(first.image.tobytes(), other.frame(123_000_000).image.tobytes())

    def test_exposure_changes_pixels_at_the_same_virtual_time(self):
        before = np.asarray(self.camera.frame(0).image).mean()
        self.camera.event('exposure', {'iso': 400}, 0)
        after = np.asarray(self.camera.frame(0).image).mean()
        self.assertGreater(after, before * 1.25)

    def test_lens_motion_uses_virtual_time_and_changes_focus(self):
        before = self.camera.frame(0).image
        self.camera.event('lens', {'focus_target': .65}, 0)
        self.assertEqual(self.camera.status(40_000_000)['lens']['focus_position'], 0)
        self.assertAlmostEqual(self.camera.status(250_000_000)['lens']['focus_position'], .2)
        focused = self.camera.frame(1_000_000_000).image
        self.assertAlmostEqual(self.camera.status(1_000_000_000)['lens']['focus_position'], .65)
        self.assertFalse(self.camera.status(1_000_000_000)['lens']['moving'])
        # Sharpness is evaluated on the static centre chart, independent of the moving marker.
        def sharpness(image):
            pixels = np.asarray(image, dtype=float)[26:78, 40:120].mean(axis=2)
            return np.abs(np.diff(pixels, axis=1)).mean()
        self.assertGreater(sharpness(focused), sharpness(before) * 1.5)

    def test_focal_length_and_aperture_change_the_rendered_image(self):
        original = self.camera.frame(0).image.tobytes()
        self.camera.event('lens', {'focal_length_mm': 24}, 0)
        self.assertFalse(original == self.camera.frame(0).image.tobytes(), '24 mm must change the field of view')
        self.camera.event('lens', {'focal_length_mm': 100}, 0)
        zoomed = self.camera.frame(0).image.tobytes()
        self.camera.event('lens', {'aperture': 8}, 0)
        self.assertNotEqual(original, zoomed)
        self.assertNotEqual(zoomed, self.camera.frame(0).image.tobytes())

    def test_external_image_is_an_actual_scene_source(self):
        path = self.root / 'scene.png'
        Image.new('RGB', (160, 104), (210, 30, 20)).save(path)
        scene = self.api.Scene.from_image(path)
        other = self.api.SoftwareCamera(scene=scene, width=160, height=104)
        other.event('power', {'on': True}, 0)
        pixels = np.asarray(other.frame(0).image, dtype=float).mean(axis=(0, 1))
        self.assertGreater(pixels[0], pixels[1] * 3)
        self.assertEqual(other.frame(0).metadata['scene']['kind'], 'image')

    def test_capture_is_a_decodable_current_frame_with_persistent_metadata(self):
        saved = self.capture()
        self.assertEqual(saved['name'], 'Z62_0001.JPG')
        raw = self.card.read(saved['name'])
        with Image.open(BytesIO(raw)) as decoded:
            decoded.load()
            self.assertEqual(decoded.size, (160, 104))
            description = json.loads(decoded.getexif()[270])
            self.assertEqual(description['frame_id'], 30)
            self.assertEqual(description['virtual_time_ns'], 1_000_000_000)
            self.assertEqual(description['implementation_level'], 'C')
        self.assertEqual(saved['sha256'], hashlib.sha256(raw).hexdigest())
        self.card.close()
        reopened = self.storage.DirectoryCard(self.root / 'card')
        self.addCleanup(reopened.close)
        self.assertEqual(reopened.read(saved['name']), raw)
        self.assertEqual(reopened.list()[0]['metadata']['frame_id'], 30)

    def test_full_press_is_one_capture_until_release(self):
        self.camera.event('shutter', {'stage': 'full', 'pressed': True}, 0)
        self.camera.event('shutter', {'stage': 'full', 'pressed': True}, 0)
        self.assertEqual(len(self.card.list()), 1)
        self.assertTrue(self.camera.status(0)['half_pressed'])
        self.camera.event('shutter', {'stage': 'full', 'pressed': False}, 0)
        self.assertFalse(self.camera.status(0)['half_pressed'])
        self.capture(0)
        self.assertEqual(len(self.card.list()), 2)

    def test_no_card_and_card_full_are_errors_without_fake_photos(self):
        other = self.api.SoftwareCamera(width=160, height=104)
        other.event('power', {'on': True}, 0)
        with self.assertRaisesRegex(self.api.CameraError, 'no_card'):
            other.event('shutter', {'stage': 'full', 'pressed': True}, 0)
        small = self.storage.DirectoryCard.create(self.root / 'small', capacity_bytes=128)
        self.addCleanup(small.close)
        limited = self.api.SoftwareCamera(card=small, width=160, height=104)
        limited.event('power', {'on': True}, 0)
        with self.assertRaisesRegex(self.storage.CardError, 'card_full'):
            limited.event('shutter', {'stage': 'full', 'pressed': True}, 0)
        self.assertEqual(small.list(), [])
        self.assertEqual(list(small.image_directory.iterdir()), [])

    def test_playback_zoom_preserves_the_file_and_delete_persists(self):
        saved = self.capture()
        before = self.card.read(saved['name'])
        self.camera.event('playback', {'action': 'open'}, 1_000_000_000)
        full = self.camera.display(1_000_000_000).image.tobytes()
        self.camera.event('zoom', {'factor': 4}, 1_000_000_000)
        self.assertNotEqual(full, self.camera.display(1_000_000_000).image.tobytes())
        self.assertEqual(self.card.read(saved['name']), before)
        self.camera.event('delete', {}, 1_000_000_000)
        self.assertEqual(self.card.list(), [])
        self.assertEqual(self.camera.status(1_000_000_000)['view'], 'live')
        self.card.close()
        reopened = self.storage.DirectoryCard(self.root / 'card')
        self.addCleanup(reopened.close)
        self.assertEqual(reopened.list(), [])
        self.camera.card = reopened
        self.assertEqual(self.capture()['name'], 'Z62_0002.JPG')

    def test_invalid_commands_cannot_create_photos_or_invalid_lens_states(self):
        for payload in ({'focus_target': float('nan')}, {'aperture': 0},
                        {'focal_length_mm': 1000}, {'focus_target': True}):
            with self.assertRaises(ValueError):
                self.camera.event('lens', payload, 0)
        for kind, payload in [('exposure', {'iso': 0}), ('power', {'on': 1}),
                              ('shutter', {'stage': 'full', 'pressed': 1}),
                              ('zoom', {'factor': 3}), ('record', {})]:
            with self.assertRaises(ValueError):
                self.camera.event(kind, payload, 0)
        self.assertEqual(self.camera.status(0)['lens']['focus_position'], 0)
        self.assertEqual(self.card.list(), [])

    def test_time_must_be_monotonic_and_power_off_releases_shutter(self):
        self.camera.event('shutter', {'stage': 'half', 'pressed': True}, 10)
        self.camera.event('power', {'on': False}, 10)
        self.assertFalse(self.camera.status(10)['half_pressed'])
        with self.assertRaisesRegex(ValueError, 'powered_off'):
            self.camera.frame(10)
        for time_ns in (9, True, -1):
            with self.assertRaises(ValueError):
                self.camera.status(time_ns)

    def test_foreign_directory_busy_card_and_external_modification_are_rejected(self):
        foreign = self.root / 'foreign'
        foreign.mkdir()
        (foreign / 'valuable.txt').write_text('preserve')
        with self.assertRaises(ValueError):
            self.storage.DirectoryCard(foreign)
        with self.assertRaises(ValueError):
            self.storage.DirectoryCard.create(foreign)
        with self.assertRaisesRegex(ValueError, 'card_busy'):
            self.storage.DirectoryCard(self.root / 'card')
        saved = self.capture()
        (self.card.image_directory / saved['name']).write_bytes(b'changed externally')
        with self.assertRaisesRegex(ValueError, 'corrupt'):
            self.card.read(saved['name'])
        with self.assertRaises(ValueError):
            self.card.read('../../valuable.txt')
        self.assertEqual((foreign / 'valuable.txt').read_text(), 'preserve')

    def test_failed_catalog_commit_does_not_publish_a_photo(self):
        import z62_directory_card as storage
        with patch.object(storage.os, 'replace', side_effect=OSError('simulated storage failure')):
            with self.assertRaises(OSError):
                self.capture()
        self.assertEqual(self.card.list(), [])
        self.assertEqual(list(self.card.image_directory.iterdir()), [])

    def test_catalog_identity_is_enforced_even_in_optimized_python(self):
        import shutil
        target = self.root / 'wrong-format'
        shutil.copytree(self.root / 'card', target)
        (target / self.storage.LOCK).unlink()
        path = target / self.storage.MANIFEST
        data = json.loads(path.read_bytes())
        data['format'] = 'foreign-directory'
        path.write_text(json.dumps(data), encoding='utf-8')
        rejected = False
        try:
            with self.storage.DirectoryCard(target):
                pass
        except ValueError:
            rejected = True
        self.assertTrue(rejected, 'An unrelated directory must never be accepted as an owned card')


if __name__ == '__main__':
    unittest.main()
