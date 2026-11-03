"""Reject stale displays and source acknowledgements without pixel evidence."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))


class SceneResponseTests(unittest.TestCase):
    def api(self):
        try:
            import z62_scene_response
        except ImportError as exc:
            self.fail('Scene response pixel verification is missing: ' + str(exc))
        return z62_scene_response

    def test_measures_source_raw_nv12_and_lcd_instead_of_counter_only(self):
        module = self.api()
        screen = Image.new('RGB', (1024, 682), (40, 40, 40))
        # OSD along the margins must not substitute for the image itself.
        ImageDraw.Draw(screen).rectangle((0, 0, 1023, 80), fill='white')
        result = module.measure(40, b'\x59\x90\x09' * 16,
            [b'\x59\x90\x09' * 16] * 4,
            [{'y': b'\x32' * 32, 'uv': b'\x80' * 32}] * 12, screen)
        self.assertTrue(result['raw_matches'])
        self.assertTrue(result['nv12_matches'])
        self.assertTrue(result['lcd_matches'])
        self.assertEqual(result['lcd_patch_medians'], [[40, 40, 40]] * 4)

    def test_detects_one_stale_raw_slot_and_wrong_nv12_chroma(self):
        module = self.api()
        raw = [b'\x11' * 48] * 4
        nv12 = [{'y': b'\x32' * 32, 'uv': b'\x80' * 32}] * 12
        screen = Image.new('RGB', (1024, 682), (40, 40, 40))
        raw[-1] = b'\x12' * 48
        self.assertFalse(module.measure(40, b'\x11' * 48, raw, nv12, screen)['raw_matches'])
        nv12[-1] = {'y': b'\x32' * 32, 'uv': b'\x00' * 32}
        self.assertFalse(module.measure(40, b'\x11' * 48, raw, nv12, screen)['nv12_matches'])
        nv12.pop()
        self.assertFalse(module.measure(40, b'\x11' * 48, raw, nv12, screen)['nv12_matches'])

    def test_green_or_old_screen_cannot_prove_gray_scene_response(self):
        module = self.api()
        for color in ((0, 210, 0), (40, 40, 40)):
            result = module.measure(210, b'\x11' * 48, [b'\x11' * 48] * 4,
                [{'y': b'\xc4' * 32, 'uv': b'\x80' * 32}] * 12,
                Image.new('RGB', (1024, 682), color))
            self.assertTrue(result['raw_matches'])
            self.assertTrue(result['nv12_matches'])
            self.assertFalse(result['lcd_matches'])

    def fixture(self):
        return [{'publish_id': 2, 'epoch': 84, 'gray': 210,
                 'frame_id': 1440, 'virtual_time_ns': 48000000000,
                 'published_virtual_seconds': 48.0, 'observed_virtual_seconds': 51.0,
                 'source': {'scene-used-publish-id': 2, 'scene-used-epoch': 84,
                            'scene-used-frame-id': 1440, 'scene-used-time-ns': 48000000000},
                 'raw_delta': 40, 'preview_delta': 40, 'source_uses_delta': 40,
                 'index': 3, 'display_enabled': True, 'ready_join': 3, 'input_inhibit': 0,
                 'measurement': {'raw_matches': True, 'nv12_matches': True, 'lcd_matches': True}},
                {'publish_id': 3, 'epoch': 84, 'gray': 40,
                 'frame_id': 1560, 'virtual_time_ns': 52000000000,
                 'published_virtual_seconds': 52.0, 'observed_virtual_seconds': 55.0,
                 'source': {'scene-used-publish-id': 3, 'scene-used-epoch': 84,
                            'scene-used-frame-id': 1560, 'scene-used-time-ns': 52000000000},
                 'raw_delta': 40, 'preview_delta': 40, 'source_uses_delta': 40,
                 'index': 3, 'display_enabled': True, 'ready_join': 3, 'input_inhibit': 0,
                 'measurement': {'raw_matches': True, 'nv12_matches': True, 'lcd_matches': True}}]

    def test_both_distinct_challenges_require_post_return_data_and_readiness(self):
        module = self.api()
        rows = self.fixture()
        self.assertTrue(module.assess(rows, 40)['new_scene_response_verified'])
        for field, value in (('raw_delta', 0), ('preview_delta', 0), ('source_uses_delta', 0),
                             ('display_enabled', False), ('ready_join', 1), ('input_inhibit', 1)):
            changed = deepcopy(rows)
            changed[-1][field] = value
            with self.subTest(field=field):
                self.assertFalse(module.assess(changed, 40)['new_scene_response_verified'])
        for field in ('raw_matches', 'nv12_matches', 'lcd_matches'):
            changed = deepcopy(rows)
            changed[-1]['measurement'][field] = False
            self.assertFalse(module.assess(changed, 40)['new_scene_response_verified'])

    def test_stale_tags_same_scene_or_pre_return_capture_cannot_pass(self):
        module = self.api()
        rows = self.fixture()
        for field in ('scene-used-publish-id', 'scene-used-epoch',
                      'scene-used-frame-id', 'scene-used-time-ns'):
            changed = deepcopy(rows)
            changed[-1]['source'][field] -= 1
            self.assertFalse(module.assess(changed, 40)['new_scene_response_verified'])
        changed = deepcopy(rows)
        changed[-1]['gray'] = 210
        self.assertFalse(module.assess(changed, 40)['new_scene_response_verified'])
        self.assertFalse(module.assess(rows, 49)['new_scene_response_verified'])
        self.assertFalse(module.assess(rows[:1], 40)['new_scene_response_verified'])
        self.assertFalse(module.assess(rows, None)['new_scene_response_verified'])

