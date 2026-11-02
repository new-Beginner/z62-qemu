"""Processor state transitions need actual native before/after bytes."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))


class ProcessorStateWriteTests(unittest.TestCase):
    def api(self):
        try:
            from trace_z62_processor_state import extract_writes
        except ImportError as exc:
            self.fail('Processor native write extraction is missing: ' + str(exc))
        return extract_writes

    def hit(self, before='01011d00', after='01041d00'):
        return {'sequence': 7, 'thread': '01', 'watch_address': '0xc1864cd0',
                'watch_before': before, 'watch_after': after,
                'watch_instruction_4': '40710020',
                'registers': {'pc': '0x103d3000', 'lr': '0x103215bd'},
                'state': {'virtual_seconds': 30.5}}

    def test_native_byte_state_transition_is_not_a_change_to_the_mode_byte(self):
        hit = self.hit()
        other = dict(hit, watch_address='0xc1868ae8')
        rows = self.api()({'hits': [other, hit]})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['before_state'], 1)
        self.assertEqual(rows[0]['after_state'], 4)
        self.assertEqual(rows[0]['before_mode'], 29)
        self.assertEqual(rows[0]['after_mode'], 29)
        self.assertEqual(rows[0]['pc'], '0x103d3000')
        self.assertEqual(rows[0]['thread'], '01')

    def test_missing_or_truncated_after_write_evidence_cannot_become_zero_state(self):
        extract = self.api()
        for after in [None, '', '0104', 'not-hex']:
            with self.subTest(after=after), self.assertRaises(ValueError):
                extract({'hits': [self.hit(after=after)]})
        with self.assertRaises(ValueError):
            extract({'hits': [self.hit(before='01')]})


if __name__ == '__main__':
    unittest.main()
