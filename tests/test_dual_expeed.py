"""Static evidence regression checks; these do not exercise real inter-chip IPC."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import analyze_dual_expeed as dual


class DualExpeedEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = ROOT / 'artifacts/z6ii-1.70'
        cls.evidence, cls.texts = dual.build_evidence(cls.folder)
        cls.views = {role: dual.FirmwareView(role, (cls.folder / spec['file']).read_bytes())
                     for role, spec in dual.SPECS.items()}

    def test_dualeg_task_ids_are_namespaced_not_concatenated_indices(self):
        for role, expected in [('master', 0x10089), ('slave', 0x10029)]:
            with self.subTest(role=role):
                binding = self.evidence['roles'][role]['dualeg']
                self.assertEqual(binding['task_id'], expected)
                self.assertEqual(binding['record']['index'], expected - 0x10000)
                self.assertEqual(binding['record']['name'], 'DUALEG')
                self.assertEqual(binding['record']['config_words'], [1, 34, 4096, 0])

    def test_initialized_data_relocation_preserves_original_bytes(self):
        for role, view in self.views.items():
            with self.subTest(role=role):
                record = self.evidence['roles'][role]['dualeg']['record']
                runtime = record['runtime_address']
                stored = view.copy_source + runtime - view.copy_destination
                self.assertEqual(view.read(runtime, 28), view.read(stored, 28))
                self.assertEqual(view.read(runtime + 16, 6), b'DUALEG')

    def test_wrong_payload_is_rejected_before_analysis(self):
        with self.assertRaisesRegex(ValueError, 'SHA-256 mismatch'):
            dual.FirmwareView('master', b'not the supplied firmware')

    def test_unbacked_addresses_and_copy_boundary_crossings_are_rejected(self):
        view = self.views['master']
        for address, size in [(0, 4), (dual.BASE, -1),
                              (view.copy_destination + view.copy_length - 1, 4),
                              (view.copy_destination + view.copy_length, 1)]:
            with self.subTest(address=address, size=size):
                with self.assertRaises(ValueError):
                    view.read(address, size)

    def test_wrong_instruction_expectation_is_not_silently_accepted(self):
        with self.assertRaises(ValueError):
            dual.require_instruction(self.views['master'], 0x103E3164, 'cmp', 'r2, #3')
        with self.assertRaisesRegex(ValueError, 'literal load'):
            self.views['master'].literal(0x103E3164)

    def test_slave_switch_data_is_not_reported_as_executable_code(self):
        table = self.evidence['slave_receive_jump_table']
        self.assertEqual(table['1'], 0x10054FEA)
        self.assertEqual(table['3'], 0x10054FEE)
        self.assertEqual(table['5'], 0x10054FF2)
        self.assertEqual(table['7'], 0x10054FF6)
        self.assertEqual(table['8'], 0x10054FFE)
        self.assertNotIn('10054fe0:', self.texts['slave.asm'])

    def test_checks_do_not_claim_runtime_or_physical_transport_validation(self):
        self.assertEqual(len(self.evidence['instruction_checks']), 58)
        self.assertTrue(all(row['passed'] for row in self.evidence['instruction_checks']))
        self.assertFalse(self.evidence['firmware_executed'])
        self.assertFalse(self.evidence['hardware_link_verified'])
        roles = self.evidence['roles']
        self.assertEqual(roles['master']['tx_ring_local_virtual_address'], 0xC7EF0000)
        self.assertEqual(roles['slave']['tx_ring_local_virtual_address'], 0xC70F0000)
        self.assertEqual(roles['slave']['second_task_records_through_dualeg_only'][0]['name'], 'MRAP_M')

    def test_evidence_generation_is_deterministic(self):
        evidence, texts = dual.build_evidence(self.folder)
        self.assertEqual(evidence, self.evidence)
        self.assertEqual(texts, self.texts)


if __name__ == '__main__':
    unittest.main()
