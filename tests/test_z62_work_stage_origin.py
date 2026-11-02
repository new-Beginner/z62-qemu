"""Actual dispatcher arguments and native writes keep uncertainty explicit."""
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


class WorkStageOriginTests(unittest.TestCase):
    def api(self):
        try:
            import trace_z62_work_stage_origin as api
        except ImportError as exc:
            self.fail('Original work stage origin observer is missing: ' + str(exc))
        return api

    def fixture(self):
        api = self.api()
        work, stage, table = 0xC2D1A9C0, 0xC2201000, 0xC2204000
        data = bytearray(128)
        struct.pack_into('<IIII', data, 0, 4, 0, 0xC2CBFBD0, 0xC2208000)
        struct.pack_into('<II', data, 0x1C, 3, 1)
        struct.pack_into('<I', data, 0x60, 3)
        obj = bytearray(48)
        struct.pack_into('<II', obj, 0, work, table)
        struct.pack_into('<I', obj, 0x24, 2)
        raw_table = bytearray(240)
        struct.pack_into('<III', raw_table, 24, 0, 0, api.NORMAL_ENTRY | 1)
        memory = Memory({(api.NORMAL_ENTRY, 4): bytes.fromhex('00f11c01'),
                         (work, 128): bytes(data), (stage, 48): bytes(obj),
                         (table, 240): bytes(raw_table)})
        regs = {'pc': api.NORMAL_ENTRY, 'lr': 0x1029A77F, 'r0': work, 'r4': stage,
                'r6': 0xC2CBFBD0, 'r7': 0xC1864A84, 'sp': 0xC541C700}
        return memory, regs

    def test_actual_dispatcher_entry_verifies_work_component_and_current_poll(self):
        api = self.api()
        memory, regs = self.fixture()
        result = api.capture(memory, regs)
        self.assertTrue(result['dispatcher_verified'])
        self.assertEqual(result['stage_index'], 2)
        self.assertEqual(result['stages'][2]['poll_pointer'], '0x102675f3')
        self.assertEqual(result['worker_pointer'], '0xc1864a84')
        self.assertNotIn('r8', regs)

    def test_other_callers_or_mismatching_table_do_not_become_dispatcher_evidence(self):
        api = self.api()
        memory, regs = self.fixture()
        regs['lr'] = 0x10200001
        self.assertFalse(api.capture(memory, regs)['dispatcher_verified'])
        self.assertNotIn((regs['r4'], 48), memory.reads)
        memory, regs = self.fixture()
        memory.rows[(0xC2204000, 240)] = b'\0' * 240
        self.assertFalse(api.capture(memory, regs)['dispatcher_verified'])
        memory, regs = self.fixture()
        regs['r6'] += 4
        self.assertFalse(api.capture(memory, regs)['dispatcher_verified'])

    def test_short_reads_and_opcode_changes_remain_errors_or_unknown(self):
        api = self.api()
        memory, regs = self.fixture()
        memory.rows[(0xC2204000, 240)] = b'\0' * 239
        with self.assertRaises(ValueError):
            api.capture(memory, regs)
        memory, regs = self.fixture()
        memory.rows[(api.NORMAL_ENTRY, 4)] = b'\0' * 4
        self.assertFalse(api.capture(memory, regs)['source_instruction_matches'])
        self.assertEqual(len(memory.reads), 1)

    def test_native_word0_and_operation_writes_require_complete_before_after(self):
        api = self.api()
        def hit(seq, address, before, after):
            return {'sequence': seq, 'thread': '01', 'state': {'virtual_seconds': 1.0},
                    'registers': {'pc': '0x10200000'}, 'watch_address': hex(address),
                    'watch_before': struct.pack('<I', before).hex(),
                    'watch_after': struct.pack('<I', after).hex(), 'watch_instruction_4': '00000000'}
        rows = api.extract_writes({'hits': [hit(1, api.WORK_ADDRESS, 4, 6),
            hit(2, api.WORK_ADDRESS+12, 0xC2208000, 0xC2209000)]})
        self.assertEqual([x['field'] for x in rows], ['word0', 'operation_pointer'])
        self.assertEqual([x['after'] for x in rows], [6, 0xC2209000])
        bad = hit(1, api.WORK_ADDRESS, 4, 6)
        bad['watch_after'] = '00'
        with self.assertRaises(ValueError):
            api.extract_writes({'hits': [bad]})


if __name__ == '__main__':
    unittest.main()
