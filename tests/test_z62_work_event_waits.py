"""Sequential event descriptors keep native frame identity and failure results."""
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))


class Memory:
    def __init__(self, rows):
        self.rows, self.reads = rows, []
        self.register_reads = []

    def read(self, address, size):
        self.reads.append((address, size))
        return self.rows[(address, size)]

    def read_register(self, name):
        self.register_reads.append(name)
        if name != 'r8':
            raise AssertionError('Unexpected register read')
        return 50


class WorkEventWaitTests(unittest.TestCase):
    def api(self):
        try:
            import trace_z62_work_event_waits as api
        except ImportError as exc:
            self.fail('Sequential native event wait observation is missing: ' + str(exc))
        return api

    def fixture(self, pc=0x102E9168):
        base = 0xC2200024
        desc = struct.pack('<III', 0xC1F59AD0, 0x80000, 0)
        return Memory({(pc, 4): bytes.fromhex('fff759ff' if pc == 0x102E9168 else '00288ed0'),
                       (base + 0x3C, 4): struct.pack('<I', 3), (base, 12): desc}), \
            {'pc': pc, 'sp': 0xC541C5E8, 'r0': base if pc == 0x102E9168 else 0,
             'r1': 50, 'r3': 0xFFFFFFFF, 'r4': 0, 'r6': base, 'r7': 7, 'r8': 50}

    def hit(self, seq, pc, when, **changed):
        _, registers = self.fixture(pc)
        registers.update(changed)
        capture = {'source_instruction_matches': True, 'identity_known': True,
                   'frame_registers': {name: hex(registers[name]) for name in ('r4', 'r6', 'r7', 'r8')},
                   'descriptor_pointer': '0xc2200024', 'descriptor_raw_0c': 'd09af5c10000080000000000',
                   'descriptor': {'event_object': '0xc1f59ad0', 'mask': 0x80000, 'group': 0},
                   'index': 0, 'selected_mask': 7, 'wait_parameter': 50}
        if pc == 0x102E916C:
            capture.update(return_r0=registers['r0'], return_r3_raw=registers['r3'])
        return {'sequence': seq, 'thread': '02',
                'registers': {key: hex(value) for key, value in registers.items()},
                'state': {'virtual_seconds': when},
                'extra_observation': {'work_event_wait': capture}}

    def test_capture_checks_actual_descriptor_argument_and_never_dereferences_return_r0(self):
        api = self.api()
        memory, registers = self.fixture()
        call = api.capture(memory, registers)
        self.assertTrue(call['identity_known'])
        self.assertEqual(call['descriptor']['mask'], 0x80000)
        self.assertEqual(call['descriptor']['event_object'], '0xc1f59ad0')
        memory, registers = self.fixture(0x102E916C)
        result = api.capture(memory, registers)
        self.assertEqual(result['return_r0'], 0)
        self.assertEqual(result['return_r3_raw'], 0xFFFFFFFF)
        self.assertNotIn((0, 12), memory.reads)
        memory, registers = self.fixture()
        registers['r0'] += 12
        self.assertFalse(api.capture(memory, registers)['identity_known'])

    def test_unknown_instruction_and_short_descriptor_do_not_become_known(self):
        api = self.api()
        memory, registers = self.fixture()
        memory.rows[(registers['pc'], 4)] = b'\0' * 4
        self.assertFalse(api.capture(memory, registers)['source_instruction_matches'])
        self.assertEqual(len(memory.reads), 1)
        memory, registers = self.fixture()
        memory.rows[(registers['r6'], 12)] = b'\0' * 11
        with self.assertRaises(ValueError):
            api.capture(memory, registers)

    def test_actual_callback_dictionary_omits_r8_and_requires_explicit_read(self):
        api = self.api()
        for pc in (0x102E9168, 0x102E916C):
            with self.subTest(pc=pc):
                memory, registers = self.fixture(pc)
                registers.pop('r8')
                result = api.capture(memory, registers)
                self.assertEqual(result['frame_registers']['r8'], '0x32')
                self.assertEqual(result['r8_source'], 'gdb-read-register')
                self.assertEqual(memory.register_reads, ['r8'])
                self.assertNotIn('r8', registers)

    def test_timeout_preserves_raw_result_and_same_frame_pair(self):
        api = self.api()
        result = api.pair_waits({'hits': [self.hit(1, 0x102E9168, 10), self.hit(2, 0x102E916C, 10.051)]})
        self.assertEqual(result['incomplete'], [])
        self.assertEqual(len(result['waits']), 1)
        self.assertEqual(result['waits'][0]['guest_seconds_wait'], 0.051)
        self.assertEqual(result['waits'][0]['return']['snapshot']['return_r0'], 0)
        self.assertFalse(result['hardware_completion_verified'])

    def test_changed_index_base_mask_or_descriptor_cannot_pair(self):
        api = self.api()
        for changed in ({'r4': 1}, {'r6': 0xC2300024}, {'r7': 1}, {'r8': 1000}, {'sp': 0xC541C5EC}):
            with self.subTest(changed=changed):
                result = api.pair_waits({'hits': [self.hit(1, 0x102E9168, 10),
                    self.hit(2, 0x102E916C, 10.051, **changed)]})
                self.assertEqual(result['waits'], [])
                self.assertTrue(result['incomplete'])
        finish = self.hit(2, 0x102E916C, 10.051)
        finish['extra_observation']['work_event_wait']['descriptor_raw_0c'] = '00' * 12
        result = api.pair_waits({'hits': [self.hit(1, 0x102E9168, 10), finish]})
        self.assertEqual(result['waits'], [])
        self.assertTrue(result['incomplete'])

    def test_open_wait_and_nonmonotone_sequences_remain_explicit(self):
        api = self.api()
        result = api.pair_waits({'hits': [self.hit(1, 0x102E9168, 10)]})
        self.assertEqual(result['waits'], [])
        self.assertEqual(len(result['incomplete']), 1)
        for seq, when in ((1, 10.051), (2, 9.99), (2, float('nan'))):
            with self.subTest(seq=seq, when=when), self.assertRaises(ValueError):
                api.pair_waits({'hits': [self.hit(1, 0x102E9168, 10), self.hit(seq, 0x102E916C, when)]})


if __name__ == '__main__':
    unittest.main()
