"""Evidence must distinguish valid pixels from a completed camera window."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))


class PairedRunEvidenceTests(unittest.TestCase):
    def api(self):
        try:
            import verify_z62_paired_run as api
        except ImportError as exc:
            self.fail('Independent resumed-run evidence verifier is missing: '+str(exc))
        return api

    def window(self):
        live = {'completed_observation': True, 'functional_acceptance_eligible': True,
                'host_debugger_attached': False, 'sources_unchanged_during_run': True}
        trace = {'process_closed': True, 'detach': 'OK', 'failure': None, 'cleanup_error': None}
        control = {'completed_observation': True, 'control_history_covers_requested_window': True,
                   'sequence_gaps': [], 'errors': [], 'final_sample_covers_requested_end_row': True,
                   'final_sample': {'known': True, 'virtual_seconds': 55.1}}
        return live, trace, control

    def pixel(self):
        row = {'kind': 'video-after', 'expected_source': {'gray': 40, 'epoch': 1, 'publish_id': 2,
                   'frame_id': 3, 'virtual_time_ns': 100_000_000, 'raw_reference': (b'\x96\x60\x09'*16).hex()},
               'source': {'scene-used-epoch': 1, 'scene-used-publish-id': 2,
                          'scene-used-frame-id': 3, 'scene-used-time-ns': 100_000_000},
               'raw_patches': [(b'\x96\x60\x09'*16).hex()]*4,
               'nv12_patches': [{'y': bytes([50]*32).hex(), 'uv': bytes([128]*32).hex()}]*12,
               'mode_heights': [1080, 576, 576], 'display_enabled': True, 'index': 3,
               'source_tags_match': True, 'pixel_response_verified': True,
               'measure': {'raw_matches': True, 'nv12_matches': True, 'lcd_matches': True,
                   'expected_y': 50, 'raw_patch_count': 4, 'nv12_patch_count': 12,
                   'lcd_patch_medians': [[40.0]*3]*4, 'lcd_tolerance': 20,
                   'lcd_chroma_tolerance': 8, 'patches_are_full_frame_checks': False}}
        return row, Image.new('RGB', (1024, 576), (40, 40, 40))

    def test_interrupted_window_cannot_pass_functional_gate(self):
        api = self.api(); live, trace, control = self.window()
        live.update(completed_observation=False, functional_acceptance_eligible=False)
        trace['process_closed'] = None
        control['final_sample'] = None
        control['completed_observation'] = False
        state = api.assess_window(live, trace, control)
        self.assertFalse(state['complete'])
        self.assertFalse(state['eligible'])

    def test_host_debugger_window_can_be_complete_but_not_eligible(self):
        api = self.api(); live, trace, control = self.window()
        live.update(host_debugger_attached=True, functional_acceptance_eligible=False)
        state = api.assess_window(live, trace, control)
        self.assertTrue(state['complete'])
        self.assertFalse(state['eligible'])

    def test_complete_claim_without_requested_end_is_rejected(self):
        api = self.api(); live, trace, control = self.window()
        control['final_sample']['virtual_seconds'] = 39.3
        with self.assertRaisesRegex(ValueError, 'window completeness'):
            api.assess_window(live, trace, control)

    def test_known_closed_window_preserves_scope(self):
        api = self.api()
        self.assertEqual(api.assess_window(*self.window()), {'complete': True, 'eligible': True})

    def test_matching_gray_with_wrong_publication_is_rejected(self):
        api = self.api(); row, image = self.pixel()
        self.assertTrue(api.replay_pixel(row, image))
        wrong = deepcopy(row); wrong['source']['scene-used-publish-id'] = 1
        with self.assertRaisesRegex(ValueError, 'source tag'):
            api.replay_pixel(wrong, image)

    def test_saved_measurement_cannot_hide_changed_lcd(self):
        api = self.api(); row, _ = self.pixel()
        with self.assertRaisesRegex(ValueError, 'pixel measurement'):
            api.replay_pixel(row, Image.new('RGB', (1024, 576), (210, 210, 210)))

    def host_profile(self):
        return {'completed_observation': True, 'sources_unchanged_during_run': True,
                'functional_acceptance_eligible': True, 'host_debugger_attached': False,
                'host_captures': [], 'host_capture_errors': []}

    def host_api(self):
        api = self.api()
        self.assertTrue(hasattr(api, 'qualify_host_context'), 'Host diagnostic scope qualification is missing')
        return api

    def test_host_capture_overrides_unaware_inner_record(self):
        api = self.host_api(); profile = self.host_profile()
        profile.update(host_captures=[{'host_debugger_attached': True}],
                       host_debugger_attached=True, functional_acceptance_eligible=False)
        state = api.qualify_host_context({'complete': True, 'eligible': True}, profile)
        self.assertEqual(state, {'complete': True, 'eligible': False})

    def test_host_capture_cannot_claim_functional_eligibility(self):
        api = self.host_api(); profile = self.host_profile()
        profile.update(host_captures=[{'host_debugger_attached': True}], host_debugger_attached=True)
        with self.assertRaisesRegex(ValueError, 'host eligibility'):
            api.qualify_host_context({'complete': True, 'eligible': True}, profile)

    def test_verified_ascii_copy_without_attach_keeps_scope(self):
        api = self.host_api()
        self.assertEqual(api.qualify_host_context({'complete': True, 'eligible': True}, self.host_profile()),
                         {'complete': True, 'eligible': True})


if __name__ == '__main__':
    unittest.main()
