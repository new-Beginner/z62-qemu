"""Resource wait returns and later cleanup keep exact native frame identity."""
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))


class Memory:
    def __init__(self, rows):
        self.rows, self.reads = rows, []

    def read(self, address, size):
        self.reads.append((address, size))
        return self.rows[(address, size)]


class StageResourceWaitTests(unittest.TestCase):
    def api(self):
        try:
            import trace_z62_stage_resource_waits as api
        except ImportError as exc:
            self.fail('Native upstream resource wait observer is missing: ' + str(exc))
        return api

    def fixture(self, pc):
        api = self.api()
        raw = bytearray(128)
        struct.pack_into('<IIII', raw, 0, 7, 0, 0xC2CBFBD0, 0xC2204000)
        struct.pack_into('<II', raw, 0x1C, 3, 1)
        struct.pack_into('<I', raw, 0x60, 3)
        base, sp = 0xC2200000, 0xC541C700
        regs = {'pc': pc, 'sp': sp, 'lr': 0x1029A77F, 'r0': 0xC18647D8,
                'r1': 0x80800000, 'r2': sp+8, 'r3': 1000, 'r4': base, 'r5': base}
        rows = {(pc, 4): bytes.fromhex(api.ANCHORS[pc]), (base, 128): bytes(raw),
                (sp+8, 4): struct.pack('<I', 0x80800000), (sp, 4): struct.pack('<I', 0x81000000),
                (0xC220400D, 2): b'\x1d\0'}
        return Memory(rows), regs

    def event(self, seq, pc, now, data, *, sp=0xC541C700, thread='02'):
        return {'sequence': seq, 'thread': thread, 'state': {'virtual_seconds': now},
                'registers': {'pc': hex(pc), 'sp': hex(sp), 'r4': '0xc2200000', 'r5': '0xc2200000'},
                'extra_observation': {'stage_resource_wait': data}}

    def test_output_return_reads_verified_stack_slot_not_clobbered_r2(self):
        api = self.api()
        m, r = self.fixture(0x1026A3A0)
        call = api.capture(m, r)
        self.assertEqual(call['arguments']['output_pointer'], '0xc541c708')
        self.assertTrue(call['arguments']['output_equals_verified_stack_slot'])
        m, r = self.fixture(0x1026A3A4)
        r.update(r0=0, r2=0x20068000)
        done = api.capture(m, r)
        self.assertEqual(done['return_r0'], 0)
        self.assertEqual(done['output_bits_raw'], 0x80800000)
        self.assertNotIn((0x20068000, 4), m.reads)
        self.assertNotIn('received_event', done)

    def test_query_interface_uses_r5_and_has_no_output_pointer(self):
        api = self.api()
        m, r = self.fixture(0x1026B552)
        r.update(r4=0x200, r1=0x200, r2=0)
        got = api.capture(m, r)
        self.assertEqual(got['work']['pointer'], '0xc2200000')
        self.assertEqual(got['arguments']['mode_raw'], 0)
        self.assertNotIn('output_bits_raw', got)
        self.assertNotIn((r['sp'], 4), m.reads)

    def test_call_return_and_cleanup_require_original_frame_and_live_identity(self):
        api = self.api()
        m, r = self.fixture(0x1026A3A0)
        call = api.capture(m, r)
        m, r = self.fixture(0x1026A3A4)
        r['r0'] = 0
        done = api.capture(m, r)
        cleanup = {'source_instruction_matches': True, 'dispatcher_return_address_matches': True,
                   'work': {**done['work'], 'pending_word4': 1}}
        hits = [self.event(1, 0x1026A3A0, 1, call), self.event(2, 0x1026A3A4, 2.006, done),
                self.event(3, api.CLEANUP, 2.006, cleanup, sp=0xC541C728)]
        result = api.correlate({'hits': hits})
        self.assertEqual(result['waits'][0]['guest_seconds_wait'], 1.006)
        self.assertEqual(len(result['cleanup_after_wait']), 1)
        self.assertEqual(result['cleanup_after_wait'][0]['cleanup']['snapshot']['work']['pending_word4'], 1)
        self.assertFalse(result['hardware_completion_verified'])
        hits[-1]['registers']['sp'] = '0xc541c72c'
        self.assertEqual(api.correlate({'hits': hits})['cleanup_after_wait'], [])

    def test_missing_return_identity_changes_and_nonmonotone_time_are_explicit(self):
        api = self.api()
        m, r = self.fixture(0x1026A3A0)
        call = api.capture(m, r)
        entry = self.event(1, 0x1026A3A0, 1, call)
        self.assertEqual(len(api.correlate({'hits': [entry]})['incomplete']), 1)
        m, r = self.fixture(0x1026A3A4)
        r['r0'] = 1
        done = api.capture(m, r)
        finish = self.event(2, 0x1026A3A4, 0.9, done)
        with self.assertRaises(ValueError):
            api.correlate({'hits': [entry, finish]})
        finish['state']['virtual_seconds'] = 2
        finish['registers']['r4'] = '0xc2300000'
        result = api.correlate({'hits': [entry, finish]})
        self.assertEqual(result['waits'], [])
        self.assertTrue(result['incomplete'])

    def test_notification_points_record_scalars_and_unknown_instructions_do_not_read_work(self):
        api = self.api()
        pc = next(iter(api.PRODUCERS))
        m = Memory({(pc, 4): bytes.fromhex(api.ANCHORS[pc])})
        d = api.capture(m, {'pc': pc, 'r0': 0xC18647D8, 'r1': 0x800000})
        self.assertTrue(d['target_event_object'])
        self.assertEqual(d['signal_mask_raw'], 0x800000)
        self.assertEqual(len(m.reads), 1)
        m = Memory({(pc, 4): b'\0' * 4})
        self.assertFalse(api.capture(m, {'pc': pc})['source_instruction_matches'])

    def test_wrong_live_output_argument_cannot_validate_the_assumed_stack_word(self):
        api = self.api()
        m, r = self.fixture(0x1026A3A0)
        r['r2'] = 0x20068000
        call = api.capture(m, r)
        self.assertNotIn((r['sp']+8, 4), m.reads)
        m, r = self.fixture(0x1026A3A4)
        r['r0'] = 1
        done = api.capture(m, r)
        result = api.correlate({'hits': [self.event(1, 0x1026A3A0, 1, call),
                                      self.event(2, 0x1026A3A4, 2, done)]})
        self.assertEqual(result['waits'], [])

    def test_output_token_source_keeps_notification_and_skip_counter_as_scalars(self):
        api = self.api()
        m = Memory({(0x10263D08, 4): bytes.fromhex('70b50d46')})
        entry = api.capture(m, {'pc': 0x10263D08, 'r0': 0x42193081, 'r1': 1})
        self.assertEqual(entry['notification_code_raw'], 0x42193081)
        self.assertEqual(entry['notification_payload_raw'], 1)
        self.assertNotIn('event_object', entry)
        self.assertEqual(len(m.reads), 1)
        m = Memory({(0x10263D1E, 4): bytes.fromhex('002802dd')})
        skipped = api.capture(m, {'pc': 0x10263D1E, 'r0': 3, 'r4': 0xC186483C, 'r5': 1})
        self.assertEqual(skipped['skip_counter_raw'], 3)
        self.assertEqual(skipped['source_payload_raw'], 1)
        self.assertEqual(len(m.reads), 1)


if __name__ == '__main__':
    unittest.main()
