# SPDX-License-Identifier: GPL-2.0-or-later
import ast
import binascii
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import z62_candidate_firmware as candidate
import run_z62_transaction as host
import run_z62_firmware as entry
import reference_updates


class CandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = candidate.load_candidate(package=ROOT / candidate.SPEC['input'])

    def test_original_package_with_explicit_coverage(self):
        record = self.original.metadata
        self.assertTrue(record['package_crc_verified'])
        self.assertTrue(record['all_executed_members_match_reference'])
        self.assertFalse(record['signature_verified'])
        self.assertFalse(record['flash_safety_verified'])
        self.assertEqual(len(record['unexecuted_members']), 2)
        self.assertTrue(all(not m['executed'] for m in record['unexecuted_members']))

    def test_members_select_modified_bytes_and_crc_is_required(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            files = dict(self.original.members)
            data = bytearray(files['master.bin'])
            data[:8] = bytes.fromhex('6200a0e3feffffea')
            data[-2:] = binascii.crc_hqx(data[:-2], 0).to_bytes(2, 'big')
            files['master.bin'] = bytes(data)
            for name, payload in files.items():
                (root / name).write_bytes(payload)
            result = candidate.load_candidate(members=root)
            self.assertEqual(dict(result.members)['master.bin'], bytes(data))
            self.assertFalse(result.metadata['all_executed_members_match_reference'])
            self.assertFalse(result.metadata['package_crc_verified'])
            self.assertGreater(result.metadata['members']['master.bin']['changed_bytes'], 0)
            data[0] ^= 1
            (root / 'master.bin').write_bytes(data)
            with self.assertRaisesRegex(ValueError, 'CRC mismatch'):
                candidate.load_candidate(members=root)
            self.assertNotEqual(dict(result.members)['master.bin'], bytes(data))

    def test_wrong_model_or_layout_is_rejected(self):
        modules = list(candidate.LAYOUT)
        modules[0] = ('ex1840_012000.bi', 208, 524290)
        with patch.object(candidate, 'read_regular', return_value=b'fixture'), \
                patch.object(candidate, 'decode', return_value=(b'', modules)):
            with self.assertRaisesRegex(ValueError, 'model/version/layout'):
                candidate.load_candidate(package=Path('unused'))

    def test_corrupt_package_crc_rejected(self):
        data = bytearray((ROOT / candidate.SPEC['input']).read_bytes())
        data[10000] ^= 1
        with patch.object(candidate, 'read_regular', return_value=bytes(data)):
            with self.assertRaisesRegex(ValueError, 'CRC mismatch'):
                candidate.load_candidate(package=Path('unused'))

    def test_valid_modified_full_package_is_accepted_and_labelled(self):
        from prepare_firmware import fw
        raw = (ROOT / candidate.SPEC['input']).read_bytes()
        tables = candidate.public_tables(candidate.XOR_SOURCE.read_text(encoding='utf-8'))
        decoded, modules = candidate.decode(raw, tables)
        plain = bytearray(decoded)
        _, offset, length = next(m for m in modules if m[0] == 'eg1850_mas_01700')
        begin, end = 32 + offset, 32 + offset + length
        plain[begin + 100] ^= 1
        plain[end-2:end] = binascii.crc_hqx(plain[begin:end-2], 0).to_bytes(2, 'big')
        plain[-16:-14] = binascii.crc_hqx(plain[32:-16], 0).to_bytes(2, 'big')
        encoded = fw.decrypt(bytes(plain), *tables)  # same XOR transform, in memory only
        with patch.object(candidate, 'read_regular', return_value=encoded):
            loaded = candidate.load_candidate(package=Path('in-memory-test.bin'))
        self.assertFalse(loaded.metadata['package']['matches_reference'])
        self.assertFalse(loaded.metadata['all_executed_members_match_reference'])
        self.assertTrue(loaded.metadata['package_crc_verified'])
        self.assertEqual(dict(loaded.members)['master.bin'][100], plain[begin+100])
        self.assertFalse(loaded.metadata['signature_verified'])
        self.assertFalse(loaded.metadata['flash_safety_verified'])

    def test_selection_and_wrong_sizes(self):
        for kw in ({}, {'package': Path('x'), 'members': Path('y')}):
            with self.assertRaisesRegex(ValueError, 'exactly one'):
                candidate.load_candidate(**kw)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'small.bin'
            path.write_bytes(b'small')
            with self.assertRaisesRegex(ValueError, 'size/type'):
                candidate.load_candidate(package=path)
            with self.assertRaisesRegex(ValueError, 'size/type'):
                candidate.read_regular(Path(folder), 1)

    def test_candidate_health_never_reads_unverified_addresses(self):
        row = candidate.candidate_health(object(), self.original.metadata)
        self.assertFalse(row['firmware_health_known'])
        self.assertFalse(row['firmware_status_empty'])
        self.assertIsNone(row['firmware_status_codes'])

    def test_missing_guest_state_is_unknown_and_process_exit_still_fails(self):
        process = SimpleNamespace(poll=lambda: None)
        machine = SimpleNamespace(process=process, phase='running', error=None)
        def unreadable():
            raise ValueError('Could not read machine state')
        row = candidate.candidate_status(machine, unreadable, self.original.metadata)
        self.assertEqual(row['phase'], 'running')
        self.assertFalse(row['ready'])
        self.assertFalse(row['firmware_health_known'])
        self.assertIn('Could not read', row['candidate_observation_error'])
        process.poll = lambda: 1
        row = candidate.candidate_status(machine, unreadable, self.original.metadata)
        self.assertEqual(row['phase'], 'failed')
        self.assertIsNotNone(row['error'])

    def test_staging_and_console_bind_exact_candidate_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            work = Path(folder)
            (work / 'inputs').mkdir()
            for name, data in self.original.members:
                (work / 'inputs' / name).write_bytes(data)
            record = {}
            candidate.install_candidate(work, record, self.original)
            self.assertFalse(record['runtime_guest_patches'])
            self.assertEqual(record['inputs']['master.bin']['sha256'],
                             self.original.metadata['members']['master.bin']['sha256'])
            source = work / 'source'
            for name in ('tools/z62_console.py', 'tools/z62_probe.py', 'tools/web_console.py',
                         'web-z62/index.html', 'web-z62/console.js'):
                dest = source / name
                dest.parent.mkdir(exist_ok=True, parents=True)
                shutil.copyfile(ROOT / 'third_party/z62-qemu' / name, dest)
            reference_updates.apply_console(source)
            host.apply_console(source)
            candidate.apply_console(source, self.original)
            text = (source / 'tools/z62_console.py').read_text(encoding='utf-8')
            ast.parse(text)
            ast.parse((source / 'tools/z62_candidate_health.py').read_text(encoding='utf-8'))
            self.assertIn('staged candidate hash/size mismatch', text)
            self.assertNotIn("source='original'", text)
            self.assertIn('state.update(candidate_health(self, CANDIDATE_INFO))', text)
            self.assertNotIn('state.update(firmware_health(self))', text)
            html = (source / 'web-z62/index.html').read_text(encoding='utf-8')
            self.assertIn('<h1>测试候选固件</h1>', html)
            self.assertNotIn('原厂菜单模拟器', html)
            (work / 'inputs/master.bin').write_bytes(b'changed outside staging')
            with self.assertRaisesRegex(ValueError, 'staging copy'):
                candidate.install_candidate(work, {}, self.original)

    def test_entry_uses_isolated_port_and_explicit_candidate(self):
        with patch.object(entry, 'load_candidate', return_value=self.original), \
                patch.object(entry.host, 'main') as run:
            entry.main(['--members', 'selected', '--experimental-parameters'])
            run.assert_called_once_with(['--experimental-parameters', '--port', '8674'],
                                        candidate=self.original)

    def test_baseline_loader_still_rejects_modified_input(self):
        import prepare_reference_firmware as baseline
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'modified.bin'
            path.write_bytes(b'candidate')
            with self.assertRaisesRegex(ValueError, 'Wrong original firmware identity'):
                baseline.prepare('z62', path, Path(folder) / 'out')


if __name__ == '__main__':
    unittest.main()
