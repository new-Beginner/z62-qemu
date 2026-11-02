"""Callback timings require the same live request and exact native frame."""
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))


class Memory:
    def __init__(self, rows):
        self.rows = rows

    def read(self, address, size):
        return self.rows[(address, size)]


class RetireCallbackTests(unittest.TestCase):
    def api(self):
        try:
            import trace_z62_retire_callback as api
        except ImportError as exc:
            self.fail('Read-only retirement callback timing is missing: ' + str(exc))
        return api

    def memory(self):
        packet = struct.pack('<4I', 0xC2200000, 7, 0, 0)
        work = bytearray(0x80)
        struct.pack_into('<I', work, 0xC, 0xC2300000)
        struct.pack_into('<I', work, 0x6C, 4)
        return {(0xC1864CD0, 8): b'\x01\x04\x1d\0\0\0\0\0',
                (0xC237A8BC, 4): struct.pack('<I', 81),
                (0xC2100000, 16): packet, (0xC2200000, 0x80): bytes(work),
                (0xC2203E30, 1): b'\x03',
                (0xC18649D4, 8): struct.pack('<II', 0xC2000010, 0x10243B01)}

    def hit(self, sequence, pc, when, *, thread='02', sp=0xC541C800,
            packet='0xc2100000', work='0xc2200000'):
        return {'sequence': sequence, 'thread': thread,
                'registers': {'pc': hex(pc), 'sp': hex(sp), 'r0': '0x43080001'},
                'state': {'virtual_seconds': when},
                'extra_observation': {'retire_callback': {'identity_known': True,
                    'packet_pointer': packet, 'work_pointer': work}}}

    def test_entry_reads_the_packet_while_return_never_dereferences_freed_memory(self):
        api = self.api()
        row = api.capture(Memory(self.memory()), {'pc': 0x103D32EE, 'r0': 0x43080001,
                          'r1': 0xC2100000, 'r4': 0xC2400000})
        self.assertEqual(row['packet_pointer'], '0xc2100000')
        self.assertEqual(row['work_pointer'], '0xc2200000')
        self.assertEqual(row['work']['flags_6c'], 4)
        self.assertEqual(row['work']['busy_3e30'], 3)
        after = api.capture(Memory({}), {'pc': 0x10295578, 'r0': 0xC2100000, 'r7': 0xC2100000})
        self.assertNotIn('packet_pointer', after)
        self.assertNotIn('work', after)

    def test_invalid_or_truncated_work_is_not_a_known_request(self):
        api = self.api()
        rows = self.memory()
        rows[(0xC2100000, 16)] = struct.pack('<4I', 0xDFFFF000, 0, 0, 0)
        row = api.capture(Memory(rows), {'pc': 0x103D32EE, 'r0': 0x43080001, 'r1': 0xC2100000})
        self.assertFalse(row['identity_known'])
        rows = self.memory()
        rows[(0xC2200000, 0x80)] = b'\0'*4
        with self.assertRaises(ValueError):
            api.capture(Memory(rows), {'pc': 0x103D32EE, 'r0': 0x43080001, 'r1': 0xC2100000})

    def test_observed_entry_argument_is_distinct_from_the_callers_saved_object(self):
        api = self.api()
        row = api.capture(Memory(self.memory()), {'pc': 0x103D32EE, 'r0': 0x43080001,
                          'r1': 0xC2100000, 'r4': 0xC18649B4})
        self.assertTrue(row.get('identity_known', False))
        self.assertEqual(row['work_pointer'], '0xc2200000')
        self.assertEqual(row['caller_dispatcher_pointer'], '0x10243b01')

    def test_exact_callback_frame_separates_entry_span_from_invocation_interval(self):
        api = self.api()
        trace = {'hits': [self.hit(1, 0x103D32EE, 31),
                         self.hit(2, 0x103D3334, 31.001, sp=0xC541C7E8),
                         self.hit(3, 0x103D3356, 31.002, sp=0xC541C7E8),
                         self.hit(4, 0x103D335A, 31.002, sp=0xC541C7E8),
                         self.hit(5, 0x10295578, 31.003)]}
        result = api.pair_callbacks(trace)
        self.assertEqual(len(result['calls']), 1)
        call = result['calls'][0]
        self.assertEqual(call['entry_to_poll_seconds'], 0.001)
        self.assertEqual(call['callback_seconds'], 0.003)
        self.assertEqual(result['incomplete'], [])
        self.assertNotIn('acknowledged', call)

    def test_wrong_cpu_stack_or_request_and_open_frames_cannot_be_paired(self):
        api = self.api()
        for changed in [dict(thread='01', sp=0xC541C7E8), dict(sp=0xC541C7EC),
                        dict(sp=0xC541C7E8, packet='0xc2500000')]:
            trace = {'hits': [self.hit(1, 0x103D32EE, 31),
                             self.hit(2, 0x103D3334, 31.001, **changed),
                             self.hit(3, 0x10295578, 31.003)]}
            with self.subTest(changed=changed):
                result = api.pair_callbacks(trace)
                self.assertEqual(result['calls'], [])
                self.assertTrue(result['incomplete'])
        result = api.pair_callbacks({'hits': [self.hit(1, 0x103D32EE, 31)]})
        self.assertEqual(result['calls'], [])
        self.assertEqual(len(result['incomplete']), 1)

    def test_unordered_or_nonfinite_native_times_are_rejected(self):
        api = self.api()
        for seq, when in [(1, 31.001), (2, float('nan'))]:
            with self.subTest(seq=seq, when=when), self.assertRaises(ValueError):
                api.pair_callbacks({'hits': [self.hit(1, 0x103D32EE, 31),
                    self.hit(seq, 0x103D3334, when, sp=0xC541C7E8)]})

    def test_list_points_out_of_order_or_missing_their_partner_remain_incomplete(self):
        api = self.api()
        for body in [[0x103D3356, 0x103D3334], [0x103D3334, 0x103D3356],
                     [0x103D3334, 0x103D335A]]:
            hits = [self.hit(1, 0x103D32EE, 31)]
            hits.extend(self.hit(n+2, pc, 31+(n+1)*0.001, sp=0xC541C7E8)
                        for n, pc in enumerate(body))
            hits.append(self.hit(5, 0x10295578, 31.004))
            with self.subTest(body=body):
                result = api.pair_callbacks({'hits': hits})
                self.assertEqual(result['calls'], [])
                self.assertTrue(result['incomplete'])


if __name__ == '__main__':
    unittest.main()
