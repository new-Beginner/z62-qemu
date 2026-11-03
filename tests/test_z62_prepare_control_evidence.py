"""Reject control runs that contain a key, media, or active capture."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from verify_z62_prepare_control_evidence import validate_no_capture


class ControlEvidenceTests(unittest.TestCase):
    def row(self):
        software = {'half_pressed': False, 'full_pressed': False, 'card': {'present': True, 'images': []}}
        return {'controls_sent': [], 'http_requests': [{'method': 'GET'}],
            'initial': {'capture': {'active_word': 0}}, 'final': {'capture': {'active_word': 0}},
            'initial_gate': {'capture_flow': {'active_word': 0}}, 'after_detach': {'capture_flow': {'active_word': 0}},
            'hits': [], 'software_before': deepcopy(software), 'software_after': deepcopy(software)}

    def test_no_control_cannot_include_even_a_rejected_post(self):
        row = self.row(); validate_no_capture(row)
        row['http_requests'].append({'method': 'POST'})
        with self.assertRaisesRegex(ValueError, 'sent a control'): validate_no_capture(row)

    def test_capture_or_photo_prevents_no_shutter_claim(self):
        for location in ('capture', 'photo'):
            row = self.row()
            if location == 'capture': row['final']['capture']['active_word'] = 1
            else: row['software_after']['card']['images'].append({'name': 'photo'})
            with self.assertRaises(ValueError): validate_no_capture(row)


if __name__ == '__main__': unittest.main()
