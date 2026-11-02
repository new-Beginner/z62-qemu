"""Offline tests only; importing the observer never starts QEMU or accesses USB."""
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from trace_z62_upper_waits import CALLS, POINTS, summarize, trace_complete, verify_instructions


def hit(label, pc, sequence, t, r0, lr='0x0', thread='1', sp='0xc532b780'):
    return {'label': label, 'sequence': sequence, 'thread': thread,
            'registers': {'pc': hex(pc), 'r0': hex(r0), 'lr': lr, 'sp': sp},
            'state': {'virtual_seconds': t}}


class UpperWaitTests(unittest.TestCase):
    def fixture(self):
        return {'hits': [
            hit('wait-call', 0x1039C318, 1, 27.144, 0xC18682AC),
            hit('wait-return', 0x1039C31C, 2, 30.160, 0),
            hit('status-producer', 0x10397EC8, 3, 30.160, 2, '0x1039c325'),
            hit('status-append', 0x103970D4, 4, 30.160, 0x35)],
            'observations': [{'status_codes': [0x35]}], 'live_anchors_verified': True,
            'process_closed': True, 'detach': 'OK'}

    def test_pair_and_duration(self):
        summary = summarize(self.fixture())
        self.assertEqual(summary['status35_callers'], ['0x1039c325'])
        self.assertEqual(summary['waits'][0]['virtual_duration'], 3.016)
        self.assertEqual(summary['waits'][0]['entry_hit'], 1)
        self.assertEqual(summary['notification_03030004_count'], 0)
        self.assertTrue(trace_complete(self.fixture()))

    def test_wrong_thread_or_stack_not_paired(self):
        for key, value in (('thread', '2'), ('sp', '0xc532b700')):
            record = self.fixture()
            if key == 'sp':
                record['hits'][1]['registers'][key] = value
            else:
                record['hits'][1][key] = value
            self.assertIsNone(summarize(record)['waits'][0]['entry_hit'])
            self.assertFalse(trace_complete(record))

    def test_unrelated_notifications_not_counted(self):
        record = self.fixture()
        record['hits'] += [hit('notification', 0x10396B6A, 5, 31, 0x03030001),
                           hit('notification', 0x10396B6A, 6, 32, 0x03030004)]
        self.assertEqual(summarize(record)['notification_03030004_count'], 1)

    def test_missing_append_sample_or_failure_rejected(self):
        for change in ({'observations': []}, {'process_closed': False}, {'detach': 'E01'},
                       {'live_anchors_verified': False}, {'failure': 'timeout'},
                       {'cleanup_error': 'disconnected'}):
            record = self.fixture()
            record.update(change)
            self.assertFalse(trace_complete(record))
        record = self.fixture()
        record['hits'].pop()
        self.assertFalse(trace_complete(record))
        self.assertFalse(trace_complete({}))

    def test_successful_wait_not_failure_evidence(self):
        record = self.fixture()
        record['hits'][1]['registers']['r0'] = '0x1'
        self.assertFalse(trace_complete(record))

    def test_original_instruction_anchors(self):
        path = ROOT / 'artifacts/z62-reference-1.70/master.bin'
        if not path.exists():
            self.skipTest('original firmware not locally available')
        anchors = verify_instructions(path.read_bytes())
        by_pc = {int(row['pc'], 16): row for row in anchors}
        self.assertEqual(len(anchors), len(POINTS))
        for call in CALLS:
            self.assertEqual(by_pc[call]['operands'], '#0x1035d43a')
            self.assertIn(by_pc[call+4]['mnemonic'], ('cbz', 'cbnz'))
        self.assertEqual(by_pc[0x10396EB6]['operands'], 'r1, #8')
        self.assertEqual(by_pc[0x10397EC8]['mnemonic'], 'push')

    def test_wrong_firmware_rejected(self):
        with self.assertRaises(ValueError):
            verify_instructions(b'not original firmware')

    def test_saved_dynamic_trace(self):
        path = ROOT / 'analysis/z62-upper-waits/init-mode-run1/trace.json'
        if not path.exists():
            self.skipTest('bounded trace not locally available')
        record = json.loads(path.read_text())
        self.assertTrue(trace_complete(record))
        summary = summarize(record)
        self.assertEqual(summary['status35_callers'], ['0x1039c325'])
        self.assertEqual(summary['notification_03030004_count'], 0)
        self.assertEqual(len(summary['waits']), 1)
        self.assertEqual(summary['waits'][0]['return_pc'], '0x1039c31c')
        entry = next(h for h in record['hits'] if h['label'] == 'wait-call')
        self.assertEqual({k: entry['registers'][k] for k in ('r0', 'r1', 'r2', 'r3')},
                         {'r0': '0xc18682ac', 'r1': '0x8', 'r2': '0x0', 'r3': '0xbb8'})
        self.assertEqual(entry['state']['cycle'], 2)


if __name__ == '__main__':
    unittest.main()
