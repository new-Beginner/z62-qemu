# SPDX-License-Identifier: GPL-2.0-or-later
"""R5 guarded adapter contracts and actual native QEMU transaction checks."""
import hashlib
import json
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import build_reference_qemu as reference
import z62_functional_device as functional
import z62_transaction_device as transaction
import probe_z62_transaction as probe

BINARY = Path(os.environ.get('Z62_TRANSACTION_QEMU', str(
    ROOT / '.build/z62-transaction-2026.10.28-r5/runtime/qemu-system-arm.exe')))


class Transaction(unittest.TestCase):
    def test_r4_identity_unchanged(self):
        manifest = json.loads((ROOT / '.build/z62-functional-2026.10.28-r4/functional-build-manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['functional_device'], functional.identity())
        binary = ROOT / '.build/z62-functional-2026.10.28-r4/runtime/qemu-system-arm.exe'
        self.assertEqual(hashlib.sha256(binary.read_bytes()).hexdigest(), manifest['binary_sha256'])

    def test_pinned_sensor(self):
        sensor = ROOT / 'third_party/z62-qemu/qemu/nikon-z62-sensor-config.c'
        self.assertEqual(hashlib.sha256(sensor.read_bytes()).hexdigest(),
                         transaction.INPUTS[sensor.name])
        self.assertFalse(transaction.identity()['default_enabled'])

    def test_reject_old_workspaces(self):
        for path in ('third_party/z62-qemu', '.build/z62-functional-2026.10.28-r4/source/qemu-10.2.4',
                     '.build/z62-reference-2026.10.27-r1/source/qemu-10.2.4'):
            with self.assertRaises(ValueError):
                transaction.apply_source(ROOT / path)
        with self.assertRaises(ValueError):
            reference.guard_workspace(ROOT / '.build/z62-functional-2026.10.28-r4', 'z62', True)

    def test_source_no_software_event_or_clock(self):
        text = transaction.HEADER.read_text(encoding='utf-8')
        for forbidden in ('timer_mod(', 'cpu_physical_memory_write(', 'qemu_clock_get_ns('):
            self.assertNotIn(forbidden, text)
        self.assertIn('sensor_mode2_configured(s)', text)
        self.assertIn('WORD(s, 0x1508) |= 2;', text)

    @unittest.skipUnless(BINARY.is_file(), 'requires built r5 manifests')
    def test_manifest_provenance(self):
        work = BINARY.parent.parent
        manifests = {name: json.loads((work / (name + '-build-manifest.json')).read_text(encoding='utf-8'))
                     for name in ('reference', 'functional', 'transaction')}
        ref = manifests['reference']
        digest = hashlib.sha256(BINARY.read_bytes()).hexdigest()
        for manifest in manifests.values():
            self.assertEqual(manifest['schema'], 1)
            self.assertEqual(manifest['binary_sha256'], digest)
            self.assertEqual(manifest['functional_device'], functional.identity())
            self.assertEqual(manifest['transaction_device'], transaction.identity())
            self.assertEqual(manifest['reference_updates'], ref['reference_updates'])
        source = work / 'source/qemu-10.2.4'
        for group, key in (('functional', 'generated_functional_sha256'),
                           ('transaction', 'generated_transaction_sha256')):
            for name, digest in manifests[group][key].items():
                self.assertEqual(hashlib.sha256((source / 'hw/arm' / name).read_bytes()).hexdigest(), digest)
                self.assertEqual(ref['prepared_source_file_sha256']['hw/arm/' + name], digest)
        old = json.loads((ROOT / '.build/z62-functional-2026.10.28-r4/functional-build-manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(manifests['transaction']['base_generated_functional_sha256'],
                         old['generated_functional_sha256'])
        probe.reference_updates.verify_binary(BINARY)  # stage(updates=True)'s exact verifier
        reference.verify_repository('z62')

    @unittest.skipUnless(sys.platform == 'win32' and BINARY.is_file(), 'requires built native r5 QEMU')
    def test_native_transaction_and_r4_regression(self):
        result = probe.run(BINARY)
        path = ROOT / 'analysis/z62-transaction-device/unittest-qtest.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
        self.assertFalse(result['firmware_loaded'])
        self.assertEqual(result['checks'][2]['real_dma_success_irq92_edges'],
                         ['IRQ raise 3', 'IRQ lower 3', 'IRQ raise 3'])


if __name__ == '__main__':
    unittest.main()
