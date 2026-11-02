"""Regression tests for the local Z6II firmware preparation and startup probe."""
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import prepare_firmware as prep
from debug_firmware import Debugger, BASE, PAYLOADS


class ContainerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = (ROOT / 'Z6_2_0170 (1).bin').read_bytes()
        cls.tables = prep.public_tables(prep.XOR_SOURCE.read_text())

    def test_original_fingerprint(self):
        self.assertEqual(prep.sha256(self.raw), prep.EXPECTED_INPUT)

    def test_all_five_modules_and_package_crc(self):
        plain, modules = prep.decode(self.raw, self.tables)
        self.assertEqual(len(modules), 5)
        sizes = {n: length - 2 for n, _, length in modules}
        self.assertEqual(sizes['eg1850_mas_01700'], 38750136)
        self.assertEqual(sizes['eg1850_sla_01700'], 8832192)
        self.assertEqual(len(plain), len(self.raw))

    def test_corrupted_payload_rejected(self):
        corrupted = bytearray(self.raw)
        corrupted[0x1000] ^= 1
        with self.assertRaisesRegex(ValueError, 'CRC mismatch'):
            prep.decode(bytes(corrupted), self.tables)

    def test_wrong_container_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Not a legacy'):
            prep.decode(b'not firmware', self.tables)

    def test_missing_or_short_tables_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Cannot find'):
            prep.public_tables('')
        with self.assertRaisesRegex(ValueError, 'expected 256'):
            prep.public_tables('Xor_Ord1[] = {0x01};')

    def test_output_does_not_clobber(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'output.bin'
            prep.write_identical_or_new(target, b'original')
            prep.write_identical_or_new(target, b'original')
            with self.assertRaisesRegex(ValueError, 'Refusing to overwrite'):
                prep.write_identical_or_new(target, b'changed')
            self.assertEqual(target.read_bytes(), b'original')

    def test_output_cannot_contain_input(self):
        with self.assertRaisesRegex(ValueError, 'must not contain'):
            prep.prepare(ROOT / 'Z6_2_0170 (1).bin', ROOT)


class DebuggerTests(unittest.TestCase):
    def debugger(self, role='master'):
        return Debugger(role, ROOT / 'artifacts/z6ii-1.70')

    def test_master_and_slave_stop_on_first_unknown_device(self):
        for role in PAYLOADS:
            with self.subTest(role=role):
                result = self.debugger(role).run()
                self.assertEqual(result['status'], 'unmodeled_memory_access')
                self.assertEqual(result['fault'], {'access': 'write', 'address': 0x04264000,
                                                 'size': 4, 'value': 0x21, 'pc': 0x1002BDA4})
                self.assertEqual(result['instruction_attempts'], 73)
                self.assertFalse(result['menu_reached'])
                self.assertFalse(result['dual_engine_ipc_modeled'])

    def test_step_follows_original_reset_branch(self):
        d = self.debugger()
        result = d.run(1)
        self.assertEqual(result['registers']['pc'], 0x1002BC88)
        self.assertEqual(result['instruction_attempts'], 1)
        self.assertEqual(result['status'], 'instruction_limit')
        self.assertIn('mov', d.disassemble()[0])

    def test_breakpoint_stops_before_instruction(self):
        d = self.debugger()
        d.breakpoints.add(0x1002BC88)
        result = d.run()
        self.assertEqual(result['status'], 'breakpoint')
        self.assertEqual(result['registers']['pc'], 0x1002BC88)
        self.assertEqual(result['instruction_attempts'], 1)
        d.breakpoints.clear()
        self.assertEqual(d.run(1)['registers']['pc'], 0x1002BC8C)

    def test_faulted_session_cannot_silently_continue(self):
        d = self.debugger()
        d.run()
        with self.assertRaisesRegex(ValueError, 'Faulted session'):
            d.run(1)

    def test_instruction_budget_validated(self):
        d = self.debugger()
        for count in (0, -1, 10_000_001):
            with self.assertRaisesRegex(ValueError, 'Instruction count'):
                d.run(count)

    def test_payload_fingerprint_rejects_changed_image(self):
        with tempfile.TemporaryDirectory() as folder:
            name, _ = PAYLOADS['master']
            (Path(folder) / name).write_bytes(b'wrong image')
            with self.assertRaisesRegex(ValueError, 'SHA-256 mismatch'):
                Debugger('master', Path(folder))


if __name__ == '__main__':
    unittest.main()
