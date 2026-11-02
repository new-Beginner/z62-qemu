"""Native wait pairs keep arguments, output bits and frame identity separate."""
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


class WorkGateWaitTests(unittest.TestCase):
    def api(self):
        try:
            import trace_z62_work_gate_wait as api
        except ImportError as exc:
            self.fail('Native resource/output wait observation is missing: ' + str(exc))
        return api

    def fixed(self):
        return {(0xC18647CC, 4): b'\0'*4,
                (0xC1864CD0, 8): b'\x01\x02\x02\0\0\0\0\0',
                (0x1026B93E, 4): bytes.fromhex('f1f03efd'),
                (0x1026B942, 4): bytes.fromhex('00980028'),
                (0x102675E4, 4): bytes.fromhex('4ef0cbfa'),
                (0x102675E8, 4): bytes.fromhex('08b10020')}

    def hit(self, seq, pc, when, *, thread='02', sp=0xC541C600, r4='0xc2200000'):
        return {'sequence': seq, 'thread': thread, 'registers': {'pc': hex(pc), 'sp': hex(sp), 'r4': r4},
                'state': {'virtual_seconds': when},
                'extra_observation': {'work_gate_wait': {'source_instruction_matches': True,
                    'phase': 'call' if pc in [0x1026B93E, 0x102675E4] else 'return'}}}

    def test_event_return_reads_the_live_stack_output_not_clobbered_r2(self):
        capture = self.api().capture
        rows = self.fixed()
        rows[(0xC541C600, 4)] = struct.pack('<I', 0xA0000000)
        call = capture(Memory(rows), {'pc': 0x1026B93E, 'sp': 0xC541C600, 'r0': 0xC18647D8,
                       'r1': 0xA0000000, 'r2': 0xC541C600, 'r3': 1000, 'r4': 0})
        self.assertEqual(call['arguments']['mask'], 0xA0000000)
        self.assertEqual(call['arguments']['wait_parameter'], 1000)
        rows[(0xC541C600, 4)] = b'\0'*4
        done = capture(Memory(rows), {'pc': 0x1026B942, 'sp': 0xC541C600,
                       'r0': 0, 'r2': 0x20068000, 'r4': 0})
        self.assertEqual(done['output_bits'], 0)
        self.assertEqual(done['return_r0'], 0)
        self.assertNotIn('acknowledged', done)

    def test_output_queue_work_identity_comes_from_output_pointer_not_r4(self):
        capture = self.api().capture
        rows = self.fixed()
        data = bytearray(128)
        struct.pack_into('<I', data, 0xC, 0)
        rows[(0xC2200000, 128)] = bytes(data)
        call = capture(Memory(rows), {'pc': 0x102675E4, 'sp': 0xC541C600,
                       'r0': 0xC18648BC, 'r1': 0xC220001C, 'r2': 50, 'r4': 0x20068000})
        self.assertEqual(call['arguments']['wait_parameter'], 50)
        self.assertEqual(call['work_pointer'], '0xc2200000')
        done = capture(Memory(self.fixed()), {'pc': 0x102675E8, 'sp': 0xC541C600, 'r0': 0})
        self.assertEqual(done['return_r0'], 0)

    def test_each_callsite_pairs_same_cpu_sp_and_preserved_r4(self):
        api = self.api()
        result = api.pair_waits({'hits': [self.hit(1, 0x1026B93E, 10),
            self.hit(2, 0x1026B942, 11.006), self.hit(3, 0x102675E4, 11.01),
            self.hit(4, 0x102675E8, 11.06)]})
        self.assertEqual([x['guest_seconds_wait'] for x in result['waits']], [1.006, 0.05])
        self.assertEqual(result['incomplete'], [])

    def test_wrong_frame_or_missing_return_cannot_be_zero_wait_success(self):
        api = self.api()
        for changed in [dict(thread='01'), dict(sp=0xC541C604), dict(r4='0xc2300000')]:
            with self.subTest(changed=changed):
                result = api.pair_waits({'hits': [self.hit(1, 0x1026B93E, 10),
                    self.hit(2, 0x1026B942, 11.006, **changed)]})
                self.assertEqual(result['waits'], [])
                self.assertTrue(result['incomplete'])
        result = api.pair_waits({'hits': [self.hit(1, 0x1026B93E, 10)]})
        self.assertEqual(result['waits'], [])
        self.assertEqual(len(result['incomplete']), 1)


if __name__ == '__main__':
    unittest.main()
