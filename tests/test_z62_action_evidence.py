"""Reject missing original context and late source binding in the r76 audit."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
import record_z62_action_evidence as evidence
from z62_action_queue_console import VERSION, decode_capture, decode_queue


class ActionEvidenceTests(unittest.TestCase):
    def row(self):
        return {'action_queue_version': VERSION, 'label': 'after-photo-released',
                'virtual_time_ns': 19_000_000_000,
                'capture_work_queue': {**decode_queue([0xC2000000, 92, 60, 0, 4, 1], [0]*1380),
                    'known_layout': True, 'header_before': [0xC2000000, 92, 60, 0, 4, 1],
                    'header_after': [0xC2000000, 92, 60, 0, 4, 1], 'header_stable_during_read': True},
                'capture_flow': decode_capture([1, 0, 3, 0x103EC499, 0, 8, 100, 0]+[0]*32),
                'applv_ram': {'words': [0]*32, 'action_word_at_c181d388': 0},
                'selector': {'scalar': {'current': 1, 'previous': 0, 'changed': 1}},
                'output': {'mode': 'photo'}, 'pipeline_mode': {'phase': 'timed-out'}}

    def test_empty_queue_does_not_imply_capture_or_mode_completion(self):
        row = evidence.summary(self.row())
        self.assertEqual(row['queue_count'], 0)
        self.assertEqual(row['capture']['stage'], '0x3')
        self.assertEqual(row['selector']['scalar']['changed'], 1)
        self.assertEqual(row['pipeline_phase'], 'timed-out')

    def test_changed_context_cannot_be_reported_as_original(self):
        row = self.row(); row['capture_flow']['outstanding'] = '0x0'
        with self.assertRaisesRegex(ValueError, 'context decoding'):
            evidence.summary(row)

    def test_binding_after_unacknowledged_shutter_send_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); case = root/'case'; case.mkdir()
            (case/'observations.jsonl').write_text(json.dumps({'kind': 'send',
                'value': {'type': 'shutter', 'outcome': 'unknown'}})+'\n', encoding='utf-8')
            target = root/'binding.json'
            with patch.object(evidence, 'ROOT', root):
                with self.assertRaisesRegex(ValueError, 'Too late'):
                    evidence.bind(root/'session', case, target)
            self.assertFalse(target.exists())

    def test_wrapper_binds_once_before_network_observation(self):
        import urllib.request
        import probe_z62_action_queue as probe
        order = []
        def scenario(url, session, output):
            req = urllib.request.Request(url+'/paired/diagnostics')
            urllib.request.urlopen(req)
            urllib.request.urlopen(req)
            return {'completed_observation': False}
        with patch.object(probe.scenario, 'run', scenario), \
             patch.object(probe.evidence, 'bind', side_effect=lambda *a: order.append('bind')), \
             patch.object(urllib.request, 'urlopen', side_effect=lambda *a: order.append('read')):
            probe.run('http://127.0.0.1:8688', Path('session'), Path('case'))
        self.assertEqual(order, ['bind', 'read', 'read'])


if __name__ == '__main__':
    unittest.main()
