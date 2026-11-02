"""Local original-function checks; no reference imports, USB, or KEY files."""
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import analyze_raw_authorization as raw


def literal_source():
    return ('MAGIC = 0x28CD7EE8\nKEYS = {"HDMIARAW.KEY": bytes.fromhex("' + '00' * 32
            + '"), "SRF_FUNC.KEY": bytes.fromhex("' + '11' * 32 + '")}\n')


class ReferenceParserTests(unittest.TestCase):
    def test_reads_only_literals_without_running_top_level_code(self):
        magic, keys = raw.reference_constants('raise RuntimeError("must not execute")\n' + literal_source())
        self.assertEqual(magic, 0x28CD7EE8)
        self.assertEqual(keys, {'HDMIARAW.KEY': bytes(32), 'SRF_FUNC.KEY': b'\x11' * 32})

    def test_rejects_executable_key_expression(self):
        source = literal_source().replace('bytes.fromhex("' + '00' * 32 + '")', '__import__("os").getcwd()')
        with self.assertRaisesRegex(ValueError, 'Only bytes.fromhex'):
            raw.reference_constants(source)

    def test_rejects_duplicate_and_wrong_size_constants(self):
        for source in (literal_source() + 'MAGIC = 1\n',
                       literal_source().replace('00' * 32, '00' * 31),
                       literal_source().replace('MAGIC = 0x28CD7EE8', 'MAGIC = True'),
                       literal_source().replace('SRF_FUNC.KEY', 'HDMIARAW.KEY')):
            with self.subTest(source=source):
                with self.assertRaises(ValueError):
                    raw.reference_constants(source)

    def test_probe_refuses_unreviewed_source_before_loading_firmware(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get('PI_SCRATCH_DIR')) as folder:
            p = Path(folder) / 'reference.py'
            p.write_text(literal_source(), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'reviewed pinned version'):
                raw.probe(p, Path(folder) / 'absent-firmware')


class OriginalAuthorizationFunctionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = raw.FunctionSandbox(ROOT / 'artifacts/z6ii-1.70')

    def tearDown(self):
        self.assertTrue(self.s.original_unchanged())

    def test_original_key_comparators_require_all_32_bytes_and_exact_length(self):
        # Independently reconstruct comparison input from original ROM tables.
        # These bytes stay in process RAM; no binary KEY is saved/distributed.
        for name, fn, table in (('HDMIARAW.KEY', 0x10437D6C, 0x12079096),
                                ('SRF_FUNC.KEY', 0x10437DA0, 0x120790C6)):
            with self.subTest(name=name):
                data, index = bytearray(32), 0
                for target in range(31, -1, -1):
                    if index % 3 == 0:
                        index += 1
                    data[target] = self.s.payload[table - raw.BASE + index]
                    index += 1
                self.assertEqual(self.s.key(fn, bytes(data))['r0'], 1)
                for target in range(32):
                    changed = bytearray(data)
                    changed[target] ^= 0x80
                    self.assertEqual(self.s.key(fn, bytes(changed))['r0'], 0)
                for length in (0, 31, 33, 0xFFFFFFFF):
                    self.assertEqual(self.s.key(fn, bytes(data), length)['r0'], 0)
                evidence = __import__('json').loads((ROOT / 'analysis/xiaohongshu-research/raw-authorization-evidence.json').read_text(encoding='utf-8'))
                self.assertEqual(hashlib.sha256(data).hexdigest(), evidence['keys'][name]['sha256'])

    def test_original_magic_check_rejects_first_generation_argument(self):
        for value, expected in ((0x28CD7EE8, raw.MAGIC_ACCEPT), (0, raw.MAGIC_ACCEPT),
                                (0x28CD7EE9, raw.MAGIC_REJECT), (0x548B3FBA, raw.MAGIC_REJECT)):
            result = self.s.call(raw.MAGIC_CHECK, stops=(raw.MAGIC_ACCEPT, raw.MAGIC_REJECT), registers={'r5': value})
            self.assertEqual(result['stop_pc'], expected)
            if expected == raw.MAGIC_REJECT:
                self.assertEqual(result['r0'], 0x201D)

    def test_original_state_setter_changes_only_target_and_stops_before_sync(self):
        for selector, offset, enabled in ((0x12, 4, 0xB2), (0x14, 5, 0x6A)):
            for requested in (0, 1, 2, 255):
                with self.subTest(selector=selector, requested=requested):
                    before = bytearray(range(32))
                    self.s.u.mem_write(self.s.config, bytes(before))
                    result = self.s.call(raw.SETTER, (selector, requested), stops=(raw.SYNC,))
                    self.assertEqual(result['stop_pc'], raw.SYNC)
                    self.assertNotIn(raw.SYNC, self.s.executed)
                    before[offset] = enabled if requested == 1 else 0
                    self.assertEqual(bytes(self.s.u.mem_read(self.s.config, 32)), bytes(before))
                    self.assertEqual(self.s.call(raw.GETTER, (selector,))['r0'], int(requested == 1))


if __name__ == '__main__':
    unittest.main()
