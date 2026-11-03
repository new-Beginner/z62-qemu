"""The interactive camera must consume committed ISP provenance, not GUI intent."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from z62_software_camera import Frame, CameraError


class PairedCameraTests(unittest.TestCase):
    def api(self):
        try:
            import z62_paired_camera as api
        except ImportError as exc:
            self.fail('Committed-frame camera adapter is missing: '+str(exc))
        return api

    def output(self, mode='video', count=3, pub=3):
        return {'schema': 1, 'enabled': True, 'valid': True, 'commits': count, 'mode': mode,
                'source': 'software-paired', 'sequence': count, 'epoch': 7, 'publish_id': pub,
                'frame_id': 3, 'time_ns': 100_000_000, 'scope': 'device-input-to-software-isp-output',
                'pixel_identity_proven': False}

    def frame(self, pub=3, revision=11, mode='video', gray=40):
        return Frame(Image.new('RGB', (4, 4), (gray,)*3),
                     {'scene_revision': revision, 'pipeline_mode': mode, 'frame_id': 3,
                      'virtual_time_ns': 100_000_000,
                      'native_scene_source': {'epoch': 7, 'publish_id': pub, 'frame_id': 3,
                                              'virtual_time_ns': 100_000_000}})

    def test_committed_frame_is_not_latest_raw_frame(self):
        api = self.api(); committed = self.frame(); raw = self.frame(pub=4, gray=210)
        exchange = SimpleNamespace(frames={3: committed, 4: raw}, consumed=raw, max_age_ns=1_000_000_000)
        frame = api.committed_frame(exchange, self.output(), 200_000_000, 11, 'video')
        self.assertEqual(frame.image.getpixel((0, 0)), (40, 40, 40))
        self.assertEqual(frame.metadata['output_lineage']['publish_id'], 3)
        self.assertIs(exchange.consumed, raw)

    def test_source_epoch_mismatch_is_rejected(self):
        api = self.api(); row = self.output(); row['epoch'] = 8
        exchange = SimpleNamespace(frames={3: self.frame()}, max_age_ns=1_000_000_000)
        with self.assertRaisesRegex(CameraError, 'tag'):
            api.committed_frame(exchange, row, 200_000_000, 11, 'video')

    def test_raw_use_without_isp_commit_cannot_capture(self):
        api = self.api(); row = self.output(); row['valid'] = False
        exchange = SimpleNamespace(frames={3: self.frame()}, max_age_ns=1_000_000_000)
        with self.assertRaisesRegex(CameraError, 'output'):
            api.committed_frame(exchange, row, 200_000_000, 11, 'video')

    def test_changed_settings_and_stale_frames_cannot_capture(self):
        api = self.api(); exchange = SimpleNamespace(frames={3: self.frame()}, max_age_ns=1_000_000_000)
        with self.assertRaisesRegex(CameraError, 'settings'):
            api.committed_frame(exchange, self.output(), 200_000_000, 12, 'video')
        with self.assertRaisesRegex(CameraError, 'stale'):
            api.committed_frame(exchange, self.output(), 2_000_000_000, 11, 'video')

    def controller(self, api):
        state = api.PipelineMode()
        state.observe(self.output('photo', 1), self.frame(mode='photo').metadata, 'photo', 11, 200_000_000)
        self.assertTrue(state.ready)
        return state

    def test_request_does_not_change_confirmed_mode(self):
        api = self.api(); state = self.controller(api)
        self.assertTrue(state.begin('video', 300_000_000, 1))
        self.assertFalse(state.begin('video', 400_000_000, 1))
        self.assertEqual(state.confirmed_mode, 'photo')
        result = state.observe(self.output('photo', 2), self.frame(mode='photo').metadata,
                               'photo', 11, 500_000_000)
        self.assertIsNone(result['apply_mode'])
        self.assertFalse(state.ready)

    def test_mode_needs_new_output_then_current_mode_frame(self):
        api = self.api(); state = self.controller(api); state.begin('video', 300_000_000, 1)
        result = state.observe(self.output('video', 2), self.frame(mode='photo').metadata,
                               'photo', 11, 500_000_000)
        self.assertEqual(result['apply_mode'], 'video')
        self.assertFalse(state.ready)
        state.applied(12, 2)
        state.observe(self.output('video', 3), self.frame(mode='photo').metadata, 'video', 12, 600_000_000)
        self.assertFalse(state.ready)
        state.observe(self.output('video', 4), self.frame(revision=12).metadata, 'video', 12, 700_000_000)
        self.assertTrue(state.ready)
        self.assertEqual(state.confirmed_mode, 'video')
        self.assertIsNone(state.requested_mode)

    def test_unknown_delivery_reconciles_without_replay(self):
        api = self.api(); state = self.controller(api); state.begin('video', 300_000_000, 1)
        state.delivery_unknown()
        self.assertFalse(state.begin('video', 400_000_000, 1))
        result = state.observe(self.output('video', 2), self.frame(mode='photo').metadata,
                               'photo', 11, 500_000_000)
        self.assertEqual(result['apply_mode'], 'video')
        self.assertFalse(state.ready)

    def test_timeout_is_not_confirmation(self):
        api = self.api(); state = self.controller(api); state.begin('video', 300_000_000, 1)
        state.observe(self.output('photo', 3), self.frame(mode='photo').metadata,
                      'photo', 11, 20_000_000_000)
        self.assertFalse(state.ready)
        self.assertEqual(state.phase, 'timed-out')
        self.assertEqual(state.confirmed_mode, 'photo')

    def test_stale_last_output_is_not_camera_ready(self):
        api = self.api(); state = self.controller(api)
        state.observe(self.output('photo', 1), self.frame(mode='photo').metadata,
                      'photo', 11, 2_000_000_000)
        self.assertFalse(state.ready)
