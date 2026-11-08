"""Bounded original STR relations; synthetic cases are not task ABI acceptance."""
import copy
from pathlib import Path
import struct
import sys
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'fenestra/z62'))
import wait_store_contract as store


class WaitStoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = store.collect()

    def event(self, role='master', tid='01'):
        p = self.contract['roles'][role]
        local = (int(tid, 16) - 1) % 2
        tcb = p['context']['geometry']['pool_end'] + 0x100
        obj, sp = tcb + 0x400, tcb + 0x1000
        handle = 0x1000003
        before = bytearray(256)
        struct.pack_into('<I', before, 0x40, sp + 16)
        after = bytearray(before)
        struct.pack_into('<I', after, 0x34, handle)
        regs = {n: 0 for n in store.REGISTERS}
        regs.update(pc=p['checkpoint'], cpsr=0x93, r0=handle, r1=tcb, r4=obj, r5=local,
                    r6=p['context']['current'], r2=0xFFFFFFFF, sp=sp, lr=p['wrapper'] + 4)
        current = [0, 0]; current[local] = tcb
        return dict(role=role, thread=tid, registers=regs, current=current,
            object_before=struct.pack('<6I', obj, obj, handle, 0, 8, 0).hex(),
            object_after=struct.pack('<6I', obj, obj, handle, 0, 8, 0).hex(),
            tcb_before=before.hex(), tcb_after=after.hex(),
            call_stack_address=sp + 16, call_stack=bytes(64).hex(),
            after_registers=dict(regs, pc=regs['pc'] + 4))

    def test_original_checkpoints(self):
        self.assertEqual(self.contract['roles']['master']['checkpoint'], 0x10120AC0)
        self.assertEqual(self.contract['roles']['slave']['checkpoint'], 0x100524B8)

    def test_four_role_cpu_relations(self):
        for role, tid in [('master','01'),('master','02'),('slave','03'),('slave','04')]:
            r = store.check_event(self.event(role, tid), self.contract['roles'][role])
            self.assertEqual(r['object_handle'], 0x1000003)
            self.assertTrue(r['handle_word_changed'])
            self.assertFalse(r['wait_registration_completed'])

    def test_already_equal_word_is_not_a_new_lifecycle(self):
        row = self.event(); row['tcb_before'] = row['tcb_after']
        result = store.check_event(row, self.contract['roles']['master'])
        self.assertFalse(result['handle_word_changed'])
        self.assertFalse(result['task_identity_verified'])

    def test_corruption_and_unbounded_reads_rejected(self):
        for name in ('cpu','role','slot','pointer','object','other-word','register','stack'):
            row = self.event()
            if name == 'cpu': row['thread'] = '05'
            elif name == 'role': row['role'] = 'slave'
            elif name == 'slot': row['current'] = [0,0]
            elif name == 'pointer': row['registers']['r4'] = 0
            elif name == 'object': row['object_after'] = '00' * 24
            elif name == 'other-word': row['tcb_after'] = '01' + row['tcb_after'][2:]
            elif name == 'register': row['after_registers']['r2'] = 0
            else: row['call_stack_address'] += 4
            with self.subTest(name=name), self.assertRaises(ValueError):
                store.check_event(row, self.contract['roles']['master'])


if __name__ == '__main__':
    unittest.main()
