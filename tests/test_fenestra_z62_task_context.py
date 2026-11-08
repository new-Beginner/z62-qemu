"""Synthetic context-anchor checks; not real task/wait ABI acceptance."""
import copy
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'fenestra/z62'))
import task_context as task


class TaskContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = task.collect()

    def event(self, role='master', thread='01', special=0):
        p = self.contract['roles'][role]
        pointer, sp = p['geometry']['pool_end'] + 0x100, p['geometry']['pool_end'] + 0x1000
        block, frame = [0] * 64, [0] * 24
        block[0xBC // 4], block[0x24 // 4] = sp, special
        frame[15], frame[16], frame[18] = 0x10104D48, 0x13, 0x10100010
        local = (int(thread, 16) - 1) % 2
        current = [0, 0]
        current[local] = pointer
        return dict(role=role, thread=thread, current=current,
            registers=dict(pc=p['checkpoint'], cpsr=0x93, lr=local,
                           r4=p['current'] + 4 * local, r8=pointer, sp=sp),
            tcb=struct.pack('<64I', *block).hex(), frame=struct.pack('<24I', *frame).hex(), frame_address=sp)

    def test_original_anchors(self):
        self.assertEqual(self.contract['roles']['master']['checkpoint'], 0x10107044)
        self.assertEqual(self.contract['roles']['slave']['checkpoint'], 0x10038A18)

    def test_two_roles_two_cpu_slots(self):
        for role, thread in (('master', '01'), ('master', '02'), ('slave', '03'), ('slave', '04')):
            r = task.check_event(self.event(role, thread), self.contract['roles'][role])
            self.assertEqual(r['resume_pc_candidate'], 0x10100010)
            self.assertFalse(r['task_identity_verified'])

    def test_special_restore_path_is_not_decoded_as_regular(self):
        r = task.check_event(self.event(special=1), self.contract['roles']['master'])
        self.assertIsNone(r['resume_pc_candidate'])
        self.assertIsNone(r['resume_cpsr_candidate'])

    def test_invalid_associations_rejected(self):
        for name in ('slot', 'saved_sp', 'frame', 'isa', 'pointer', 'pc'):
            e = self.event()
            if name == 'slot': e['current'][0] = 0
            elif name == 'saved_sp': e['registers']['sp'] += 4
            elif name == 'frame': e['frame'] = e['frame'][:-2]
            elif name == 'isa': e['registers']['cpsr'] |= 32
            elif name == 'pointer': e['registers']['r8'] = 0
            else: e['registers']['pc'] += 4
            with self.subTest(name=name), self.assertRaises(ValueError):
                task.check_event(e, self.contract['roles']['master'])

    def test_range_is_bounded(self):
        p = self.contract['roles']['master']
        self.assertTrue(task.bounded_ram(p, p['geometry']['start'], 256))
        self.assertFalse(task.bounded_ram(p, p['geometry']['end'] - 4, 256))
        self.assertFalse(task.bounded_ram(p, p['geometry']['start'] + 1, 4))
        self.assertFalse(task.bounded_ram(p, p['geometry']['start'], -4))
        self.assertFalse(task.bounded_ram(p, p['geometry']['start'], 8192))

    def test_cpu_role_cannot_alias_modulo_two(self):
        e = self.event()
        e['thread'] = '05'
        with self.assertRaises(ValueError):
            task.check_event(e, self.contract['roles']['master'])
        e['thread'] = '03'
        with self.assertRaises(ValueError):
            task.check_event(e, self.contract['roles']['master'])


if __name__ == '__main__':
    unittest.main()
