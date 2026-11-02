"""离线合同测试：固定固件、真实 LDR/STR 锚点及主机侧字段算术。"""
import importlib.util
from pathlib import Path
import struct
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "z62_ingress_contract", ROOT / "tools/analyze_z62_ingress_contract.py")
contract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(contract)


class ContractArithmeticTests(unittest.TestCase):
    def test_geometry_matches_supplied_observation(self):
        descriptor = bytearray(0x1C)
        struct.pack_into("<I", descriptor, 0, 1)
        descriptor[5] = 2
        struct.pack_into("<H", descriptor, 6, 1514)
        struct.pack_into("<H", descriptor, 0xA, 1006)
        values = contract.geometry_registers(descriptor)
        self.assertEqual(values[0x20069514], 6)
        self.assertEqual(values[0x20069518], 0x05EA0000)
        self.assertEqual(values[0x2006951C], 0x03EE0000)

    def test_halfword_order_and_auxiliary_fields(self):
        d = bytearray(0x1C)
        struct.pack_into("<HH", d, 6, 0x1234, 0x5678)
        struct.pack_into("<HH", d, 0x18, 0xABCD, 0xEF01)
        d[0x14] = 0x9A
        struct.pack_into("<H", d, 0x16, 0xBCDE)
        result = contract.geometry_registers(d)
        self.assertEqual(result[0x20069518], 0x12345678)
        self.assertEqual(result[0x20069524], 0xABCDEF01)
        self.assertEqual(result[0x20069528], 0x009ABCDE)

    def test_stride_formulas_not_packing(self):
        self.assertEqual(contract.stride_from_fields(1514, 0), 3040)
        self.assertEqual(contract.stride_from_fields(1514, 1), 2656)
        self.assertEqual(contract.stride_from_fields(1514, 2), 2272)
        self.assertEqual(contract.stride_from_fields(1514, 2, 2304), 2304)
        self.assertEqual(contract.stride_from_fields(65535, 0), 0)
        # Firmware floors before alignment; this is NOT generic ceil(12*w/8).
        self.assertEqual(contract.stride_from_fields(11, 2), 16)

    def test_all_channel_address_banks(self):
        addresses = [0x44000000 + 0x100000 * i for i in range(4)]
        for channel in range(4):
            for bank in range(2):
                base = 0x20069800 + channel * 0x100
                values = contract.channel_registers(channel, bank, addresses, 2272)
                self.assertEqual(values[base + 8], 2272)
                for slot in range(4):
                    self.assertEqual(values[base + 0x50 + bank * 16 + slot * 4],
                                     addresses[slot])

    def test_invalid_inputs_rejected_by_host_helpers(self):
        with self.assertRaises(ValueError):
            contract.geometry_registers(bytes(12))
        with self.assertRaises(ValueError):
            contract.stride_from_fields(1514, 3)
        with self.assertRaises(ValueError):
            contract.channel_registers(4, 0, [0] * 4, 10)
        with self.assertRaises(ValueError):
            contract.channel_registers(2, 2, [0] * 4, 10)

    def test_wrong_hash_rejected(self):
        with self.assertRaisesRegex(ValueError, "SHA256 mismatch"):
            contract.verify_image(b"not the fixed image")


class FixedFirmwareEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not contract.IMAGE.is_file():
            raise unittest.SkipTest("fixed firmware not present")
        cls.data = contract.IMAGE.read_bytes()
        cls.evidence, cls.listing = contract.extract(cls.data)

    def test_fixed_hash_and_instruction_anchors(self):
        self.assertEqual(contract.verify_image(self.data), contract.SHA256)
        contract.verify_anchors(self.data)

    def test_actual_literal_consumer(self):
        refs = {r["instruction"]: r for r in self.evidence["literal_consumers"]}
        self.assertEqual(refs[0x102090AA]["pool"], 0x10209348)
        self.assertEqual(refs[0x102090AA]["value"], 0x20069500)
        self.assertEqual(refs[0x10209248]["value"], 0x20069A14)

    def test_actual_caller_chain(self):
        branches = {(b["instruction"], b["target"])
                    for b in self.evidence["bounded_direct_branches"]}
        for edge in [(0x102397F6, 0x1020C2D4), (0x1020C2DC, 0x102090A0),
                     (0x10239760, 0x1020C340), (0x1020C348, 0x102091FE),
                     (0x1023976C, 0x1020C358), (0x1020C362, 0x10209296)]:
            self.assertIn(edge, branches)

    def test_raw_matches_not_promoted_to_xrefs(self):
        self.assertIn(0x1031E5A4, self.evidence["integer_occurrences_NOT_xrefs"])
        insn = next(contract.decoder().disasm(
            self.data[0x1031E5A4-contract.BASE:0x1031E5A8-contract.BASE], 0x1031E5A4))
        self.assertEqual(insn.mnemonic, "str")
        self.assertIsNone(contract.literal_reference(insn, self.data))

    def test_bounds_and_unknowns(self):
        self.assertLess(sum(b-a for _, a, b in contract.WINDOWS), 4096)
        self.assertEqual(self.evidence["packing"], "unknown")
        self.assertEqual(self.evidence["dma_safety"], "not established")
        self.assertFalse(self.evidence["firmware_executed"])


if __name__ == "__main__":
    unittest.main()
