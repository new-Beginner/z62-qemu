"""Memory geometry/parser tests use synthetic inputs only."""
import importlib.util
from pathlib import Path
import struct
import sys
import unittest

P=Path(__file__).resolve().parents[1]/'fenestra/z62'
sys.path.insert(0,str(P))
spec=importlib.util.spec_from_file_location('fenestra_memory_contract',P/'memory_contract.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class MemoryContractTests(unittest.TestCase):
    def test_arm_call_signed_target_and_opcode(self):
        self.assertEqual(m.arm_call(struct.pack('<I',0xEB000001),m.BASE),m.BASE+12)
        self.assertEqual(m.arm_call(struct.pack('<I',0xEBFFFFFE),m.BASE),m.BASE)
        with self.assertRaisesRegex(ValueError,'ARM BL'):
            m.arm_call(struct.pack('<I',0xEA000001),m.BASE)

    def test_known_geometry_and_alignment(self):
        g=m.pool_geometry(0xB2C00000,0xB5F00000)
        self.assertEqual((g['pool_end'],g['count']),(0xB2C33000,26010))
        self.assertEqual(m.pool_geometry(1,0x10000)['start'],8)
        self.assertEqual(m.pool_geometry(0,0x10000)['pool_end'],0x800)

    def test_geometry_rejects_small_reversed_or_overflow(self):
        for start,end in [(-1,0x10000),(0x10000,0),(0,0x1000),(0,2**32+1),(2**32-16,2**32)]:
            with self.subTest(start=start,end=end),self.assertRaises(ValueError):
                m.pool_geometry(start,end)

    def test_list_group_flags_are_independent(self):
        rows=m.list_groups(0x1000)
        self.assertEqual([(r['flags'],r['base']) for r in rows],
                         [(0,0x1018),(0x10,0x1000),(0x300,0x1050),(0x310,0x1038)])
        self.assertEqual(len({r['base'] for r in rows}),4)
        with self.assertRaises(ValueError):m.list_groups(0x1001)
        with self.assertRaises(ValueError):m.list_groups(2**32-4)

    def test_private_identity_required(self):
        for role in ('master','slave'):
            with self.subTest(role=role),self.assertRaisesRegex(ValueError,'original Z62'):
                m.profile(bytes(4),role)


if __name__=='__main__':unittest.main()
