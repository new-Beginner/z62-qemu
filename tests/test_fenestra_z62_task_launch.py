"""Synthetic contracts test tooling, not native failure/lifetime acceptance."""
from pathlib import Path
import struct
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'fenestra/z62'))
import task_launch_contract as t


class LaunchContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c = t.collect()

    def regs(self):
        r = {n: i for i, n in enumerate(t.REGISTERS)}
        r.update(sp=0xC3001000, lr=0x10104000, pc=0x1010A91C, cpsr=0x13)
        return r

    def test_original_index3_and_all_pop_exits(self):
        for role, a in [('master', 0x1010A91C), ('slave', 0x1003C2F0)]:
            p = self.c['roles'][role]
            self.assertEqual(p['start'], a)
            self.assertEqual(p['returns'], [a+0x5C, a+0x9C, a+0x26C])
            self.assertEqual(p['service_table_words'][3], a)
            self.assertNotEqual(p['service_table_words'][10], a)

    def test_push_effect_and_written_words(self):
        r = self.regs()
        after = dict(r, pc=r['pc']+4, sp=r['sp']-40)
        raw = struct.pack('<10I', *[r[n] for n in t.SAVED])
        t.check_push({'registers': r, 'after_registers': after, 'after_stack': raw.hex()})
        with self.assertRaises(ValueError):
            t.check_push({'registers': r, 'after_registers': after, 'after_stack': ('00'*40)})

    def test_pop_arm_thumb_restores_actual_words(self):
        for lr in (0x10104000, 0x103DEBC7):
            start = self.regs(); start['lr'] = lr
            before = dict(start, pc=0x1010AB88, sp=start['sp']-40, r0=0)
            saved = [start[n] for n in t.SAVED]
            after = dict(before, **dict(zip(t.SAVED[:-1], saved[:-1])), sp=start['sp'],
                         pc=lr & ~1, cpsr=0x13 | (32 if lr & 1 else 0))
            e = dict(registers=before, after_registers=after, saved_stack=struct.pack('<10I', *saved).hex())
            t.check_pop(e, {'registers': start})
            e['after_registers'] = dict(after, sp=after['sp']+4)
            with self.assertRaises(ValueError): t.check_pop(e, {'registers': start})

    def test_table_mapping_is_local_and_exact(self):
        p = self.c['roles']['master']; r = self.regs(); r.update(r0=0x01000003, r1=0x1234)
        base = 0xC3002000; b = bytearray(216); struct.pack_into('<I', b, 8, r['r0'])
        e = dict(registers=r, table_words=[base, 100], tcb_address=base+432, tcb=b.hex())
        self.assertEqual(t.check_input(e, p)['tcb_address'], base+432)
        for name in ('foreign-handle', 'index-zero', 'table-count', 'foreign-tcb'):
            import copy
            bad = copy.deepcopy(e)
            if name == 'foreign-handle': bad['tcb'] = '00'*216
            elif name == 'index-zero': bad['registers']['r0'] = 0x01000000
            elif name == 'table-count': bad['table_words'][1] = 2
            else: bad['tcb_address'] += 216
            with self.subTest(name=name), self.assertRaises(ValueError): t.check_input(bad, p)

    def test_ambiguous_live_stack_rejected(self):
        row = {'role': 'master', 'registers': {'sp': 1000}}
        pair = {'role': 'master', 'input': {'registers': {'sp': 1040}}, 'returned': None}
        self.assertEqual(t.stack_matches([pair], row), [pair])
        with self.assertRaises(ValueError): t.stack_matches([pair, pair], row)
    def test_bootstrap_svc_stack_uses_native_ram_guard_not_heap_guard(self):
        import json
        e = json.loads((t.ROOT/'analysis/fenestra-z62-task-launch-r15/run-1.json').read_text())['failure_event']
        self.assertEqual(t.check_input(e, self.c['roles'][e['role']])['handle'], e['registers']['r0'])


    def test_scope_keeps_full_port_and_lifecycle_unverified(self):
        self.assertFalse(self.c['complete_task_abi_verified'])
        self.assertFalse(self.c['task_lifetime_verified'])
        self.assertFalse(self.c['startup_failure_matrix_verified'])


if __name__ == '__main__': unittest.main()
