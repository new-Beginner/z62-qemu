# SPDX-License-Identifier: GPL-2.0-or-later
"""Bounded RAW contract + native Windows QEMU integration (no firmware)."""
import hashlib
import json
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import build_reference_qemu as reference
import reference_updates
import z62_functional_device as functional
import probe_z62_functional_raw as probe

BINARY = Path(os.environ.get('Z62_FUNCTIONAL_QEMU', str(
    ROOT / '.build/z62-functional-2026.10.28-r4/runtime/qemu-system-arm.exe')))


class RawContract(unittest.TestCase):
    def test_experimental_packing(self):
        frame = probe.pattern()
        self.assertEqual(len(frame), 2272 * 1006)
        self.assertEqual(frame[:3], bytes((0x00, 0x31, 0x10)))
        self.assertEqual(frame[2271::2272], bytes(1006))
        self.assertEqual(probe.WIDTH * 12 // 8 + 1, probe.STRIDE)

    def test_pinned_input(self):
        data = (ROOT / 'third_party/z62-qemu/qemu/nikon-z72-input-config.c').read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(), functional.INPUTS['nikon-z72-input-config.c'])
        self.assertEqual(reference_updates.VERSION, '2026.10.27-r1')
        self.assertFalse(functional.identity()['default_enabled'])
        self.assertFalse(functional.identity()['sensor_completion_source'])

    def test_protected_old_workspace(self):
        with self.assertRaises(ValueError):
            reference.guard_workspace(ROOT / '.build/z62-reference-2026.10.27-r1', 'z62', True)
        with self.assertRaises(ValueError):
            functional.apply_source(ROOT / 'third_party/z62-qemu')

    def test_guarded_replace_rejects_duplicate(self):
        with self.assertRaises(ValueError):
            reference_updates.replace_once('anchor anchor', 'anchor', 'replacement')

    @unittest.skipUnless(BINARY.is_file() and sys.platform == 'win32',
                         'requires built native Windows functional QEMU')
    def test_native_qtest(self):
        result = probe.run(BINARY)
        evidence = ROOT / 'analysis/z62-functional-device/unittest-qtest.json'
        evidence.parent.mkdir(parents=True, exist_ok=True)
        evidence.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
        self.assertFalse(result['firmware_loaded'])
        self.assertTrue(result['checks'][2]['engine_local_root_verified'])


if __name__ == '__main__':
    unittest.main()
