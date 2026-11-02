"""Cancellation evidence requires native frame and live descriptor identity."""
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


class WorkSignalRouteTests(unittest.TestCase):
    def api(self):
        try:
            import trace_z62_work_signal_route as api
        except ImportError as exc:
            self.fail('Native signal route observation is missing: ' + str(exc))
        return api

    def work(self):
        raw = bytearray(128)
        struct.pack_into('<IIII', raw, 0, 7, 1, 0xC2008000, 0xC2009000)
        struct.pack_into('<II', raw, 0x1C, 3, 3)
        for i in range(3):
            struct.pack_into('<III', raw, 0x24 + 12*i, 0xC1F59AD0, 1 << i, 0)
        struct.pack_into('<I', raw, 0x60, 3)
        return bytes(raw)

    def hit(self, seq, pc, when, data, *, sp=0xC541C700, thread='02', **registers):
        regs = {'pc': pc, 'sp': sp, 'r0': 1, 'r1': 0, 'r4': 0xC2200000, 'lr': 0}
        regs.update(registers)
        return {'sequence': seq, 'thread': thread, 'state': {'virtual_seconds': when},
                'registers': {k: hex(v) for k, v in regs.items()},
                'extra_observation': {'work_signal_route': {'source_instruction_matches': True, **data}}}

    def cancel_sequence(self, counter=3):
        api = self.api()
        raw = bytearray(self.work())
        struct.pack_into('<I', raw, 0x20, counter)
        work = api.decode_work(0xC2200000, bytes(raw))
        pointer = 0xC2200024 + 12*(counter-1)
        desc = work['descriptors'][counter-1]
        return [self.hit(1, api.CANCEL_CALL, 10, {'work': work}),
                self.hit(2, api.SIGNAL_ENTRY, 10.001, {'descriptor_pointer': hex(pointer),
                    'descriptor': desc}, sp=0xC541C6D8),
                self.hit(3, api.SIGNAL_SET, 10.001, {'event_object': desc['event_object'], 'mask': desc['mask']},
                    sp=0xC541C6D8),
                self.hit(4, api.CANCEL_STORE, 10.001, {'counter_address': '0xc2200020', 'counter_value': counter-1},
                    sp=0xC541C6F0),
                self.hit(5, api.CANCEL_RETURN, 10.002, {'work_pointer': '0xc2200000', 'return_r0': 1})]

    def test_return_and_native_store_capture_never_read_released_work(self):
        api = self.api()
        for pc, registers in ((api.CANCEL_RETURN, {'r0': 1, 'r4': 0xC2200000}),
                              (api.CANCEL_STORE, {'r0': 2, 'r4': 0xC220001C})):
            with self.subTest(pc=pc):
                m = Memory({(pc, 4): bytes.fromhex(api.ANCHORS[pc])})
                result = api.capture(m, {'pc': pc, **registers})
                self.assertEqual(len(m.reads), 1)
                self.assertTrue(result['source_instruction_matches'])

    def test_live_work_keeps_identity_words_and_descriptor_layout(self):
        api = self.api()
        raw = self.work()
        m = Memory({(api.CANCEL_CALL, 4): bytes.fromhex(api.ANCHORS[api.CANCEL_CALL]),
                    (0xC2200000, 128): raw})
        got = api.capture(m, {'pc': api.CANCEL_CALL, 'r0': 0xC18648BC,
                             'r1': 0xC220001C, 'r4': 0xC2200000})
        self.assertEqual(got['work']['counter_word20'], 3)
        self.assertEqual([d['mask'] for d in got['work']['descriptors']], [1, 2, 4])
        other = bytearray(raw)
        struct.pack_into('<I', other, 0, 8)
        self.assertNotEqual(api.decode_work(0xC2200000, bytes(other))['identity'], got['work']['identity'])
        m.rows[(0xC2200000, 128)] = raw[:-1]
        with self.assertRaises(ValueError):
            api.capture(m, {'pc': api.CANCEL_CALL, 'r0': 0xC18648BC,
                            'r1': 0xC220001C, 'r4': 0xC2200000})

    def test_native_cancel_frame_and_exact_descriptor_match(self):
        api = self.api()
        result = api.correlate({'hits': self.cancel_sequence()})
        self.assertEqual(len(result['cancellations']), 1)
        self.assertEqual(result['incomplete_cancellations'], [])
        cancel = result['cancellations'][0]
        self.assertTrue(cancel['local_route_verified'])
        self.assertEqual(cancel['dispatched_descriptor_indices'], [2])
        self.assertFalse(result['exclusive_producer_verified'])
        self.assertFalse(result['hardware_completion_verified'])

    def test_other_cpu_or_wrong_stack_descriptor_or_counter_cannot_prove_route(self):
        api = self.api()
        for change in ('cpu', 'sp', 'descriptor', 'counter'):
            with self.subTest(change=change):
                hits = self.cancel_sequence()
                if change == 'cpu':
                    hits[1]['thread'] = '01'
                elif change == 'sp':
                    hits[1]['registers']['sp'] = '0xc541c6dc'
                elif change == 'descriptor':
                    hits[1]['extra_observation']['work_signal_route']['descriptor_pointer'] = '0xc230003c'
                else:
                    hits[3]['extra_observation']['work_signal_route']['counter_value'] = 1
                result = api.correlate({'hits': hits})
                self.assertFalse(result['cancellations'][0]['local_route_verified'])
        hits = self.cancel_sequence()[:-1]
        self.assertEqual(len(api.correlate({'hits': hits})['incomplete_cancellations']), 1)

    def test_reordered_events_and_untrusted_opcodes_do_not_become_completion(self):
        api = self.api()
        hits = self.cancel_sequence()
        hits[1]['sequence'] = 1
        with self.assertRaises(ValueError):
            api.correlate({'hits': hits})
        m = Memory({(api.CANCEL_CALL, 4): b'\0' * 4})
        self.assertFalse(api.capture(m, {'pc': api.CANCEL_CALL})['source_instruction_matches'])
        self.assertEqual(len(m.reads), 1)

    def test_cancel_association_requires_complete_set_and_same_work_identity(self):
        api = self.api()
        hits = []
        for i, count in enumerate((3, 2, 1)):
            part = self.cancel_sequence(count)
            for event in part:
                event['sequence'] += 5*i
                event['state']['virtual_seconds'] += 0.1*i
            hits.extend(part)
        raw = bytearray(self.work())
        struct.pack_into('<I', raw, 0x20, 0)
        for word0, returned in ((7, 1), (8, 1), (7, 0)):
            with self.subTest(word0=word0, returned=returned):
                struct.pack_into('<I', raw, 0, word0)
                call = self.hit(16, api.WORK_CALL, 11, {'work': api.decode_work(0xC2200000, bytes(raw))})
                ret = self.hit(17, api.WORK_RETURN, 11.001, {'return_r0': returned})
                result = api.correlate({'hits': [*hits, call, ret]})
                self.assertEqual(result['work_waits'][0]['all_descriptor_cancel_routes_observed'],
                                 word0 == 7 and returned == 1)


if __name__ == '__main__':
    unittest.main()
