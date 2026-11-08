"""Synthetic parser tests; do not need or alter private firmware."""
import importlib.util
from pathlib import Path
import struct
import unittest

P = Path(__file__).resolve().parents[1]/'fenestra/z62/startup_contract.py'
spec = importlib.util.spec_from_file_location('fenestra_startup',P)
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


class StartupContractTests(unittest.TestCase):
    def test_arm_branch_positive_and_negative(self):
        self.assertEqual(c.arm_branch(struct.pack('<I',0xEA000001),0),c.BASE+12)
        self.assertEqual(c.arm_branch(struct.pack('<I',0xEAFFFFFE),0),c.BASE)
        with self.assertRaisesRegex(ValueError,'unconditional'):
            c.arm_branch(bytes(4),0)

    def test_literal_register_and_direction(self):
        image = struct.pack('<4I',0xE59F0000,0,0x12345678,0xE51F100C)
        self.assertEqual(c.arm_literal(image,0,0),0x12345678)
        self.assertEqual(c.arm_literal(image,12,1),0x12345678)
        with self.assertRaisesRegex(ValueError,'literal'):
            c.arm_literal(image,0,1)

    def image(self,records):
        return b''.join(struct.pack('<4I',*r) for r in records)+bytes(18)

    def test_scatter_copy_and_large_zero(self):
        data=self.image([(c.BASE,0xC1800000,4,c.BASE+0x6C),
                         (0xFFFFFFFF,0x80000000,0x40000000,c.BASE+0x88)])
        rows=c.scatter(data,0)
        self.assertEqual([r['kind'] for r in rows],['copy','zero'])
        self.assertEqual(rows[0]['source_sha256'],c.sha(data[:4]))
        self.assertNotIn('source_sha256',rows[1])

    def test_scatter_rejects_invalid(self):
        records=[(c.BASE,0xC1800000,4,c.BASE+0x70),
                 (c.BASE,0xC1800001,4,c.BASE+0x6C),
                 (c.BASE,0xC1800000,0,c.BASE+0x6C),
                 (c.BASE,0xFFFFFFFC,8,c.BASE+0x88),
                 (c.BASE-4,0xC1800000,4,c.BASE+0x6C),
                 (c.BASE+100,0xC1800000,4,c.BASE+0x6C)]
        for record in records:
            with self.subTest(record=record),self.assertRaises(ValueError):
                c.scatter(self.image([record]),0)
        with self.assertRaisesRegex(ValueError,'Truncated'):
            c.scatter(bytes(15),0)
        with self.assertRaisesRegex(ValueError,'Unterminated'):
            c.scatter(self.image([(c.BASE,0xC1800000,4,c.BASE+0x6C)]),0,max_records=0)

    def test_short_section_fields_and_rejection(self):
        data=bytearray(0x14000)
        struct.pack_into('<I',data,0x10000+0xC18*4,0xC1814426)
        row=c.section(data,0xC1801234)
        self.assertEqual(row['physical_address'],0xC1801234)
        self.assertEqual(row['domain'],1)
        self.assertEqual(row['ap_bits'],1)
        struct.pack_into('<I',data,0x10000+0xC18*4,0xC181C426)
        self.assertEqual(c.section(data,0xC1801234)['ap_bits'],5)
        self.assertFalse(row['xn'])
        with self.assertRaisesRegex(ValueError,'ordinary'):
            c.section(data,0x10000000)
        with self.assertRaises(ValueError):
            c.section(data,2**32)

    def test_original_identity_gate(self):
        for role in c.PROFILES:
            with self.subTest(role=role), self.assertRaisesRegex(ValueError,'original Z62'):
                c.analyze(bytes(4),role)

    def test_instruction_state_and_truncation(self):
        self.assertEqual(c.instructions(bytes.fromhex('70470000'),c.BASE,2,True)[0]['mnemonic'],'bx')
        with self.assertRaisesRegex(ValueError,'outside'):
            c.instructions(bytes.fromhex('70470000'),c.BASE,4,True)


if __name__=='__main__':
    unittest.main()
