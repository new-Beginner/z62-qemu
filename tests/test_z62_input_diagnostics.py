"""Offline rejection tests for the experimental ready-event diagnostic."""
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from trace_z62_capture_setup import ready_route_diagnostic, metadata_route_diagnostic
from probe_z62_liveview import expected_raw_prefix
from decompile_z62 import audit_exports


class ReadyDiagnosticTests(unittest.TestCase):
    def machine(self, frames=2, masks=None):
        masks = masks or {0x20068200: 0x18, 0x20068260: 0x21, 0x20068280: 0x80}
        return SimpleNamespace(qmp=SimpleNamespace(command=Mock(return_value=frames)),
            _words=Mock(side_effect=lambda address, count: [masks[address]]), _qtest=Mock())

    def run_diagnostic(self, machine, all_ready=True, payload=None):
        with patch('probe_z62_liveview.master_event_path', return_value='/master'), \
             patch('probe_z62_liveview.qtest_read', return_value=expected_raw_prefix() if payload is None else payload):
            return ready_route_diagnostic(machine, entire_set=all_ready)

    def test_no_irq_without_actual_dma_count(self):
        for value in (0, -1, None, True, '2'):
            machine = self.machine(value)
            self.assertIsNone(self.run_diagnostic(machine))
            machine._qtest.assert_not_called()

    def test_one_disabled_cause_rejects_entire_set_without_partial_injection(self):
        machine = self.machine(masks={0x20068200: 0x18, 0x20068260: 0x20, 0x20068280: 0x80})
        self.assertIsNone(self.run_diagnostic(machine))
        machine._qtest.assert_not_called()

    def test_bad_pixels_reject_before_any_irq(self):
        machine = self.machine()
        with self.assertRaisesRegex(ValueError, 'readback mismatch'):
            self.run_diagnostic(machine, payload=bytes(32))
        machine._qtest.assert_not_called()

    def test_raw_only_does_not_emit_unmodeled_statistic_notifications(self):
        machine = self.machine()
        result = self.run_diagnostic(machine, all_ready=False)
        self.assertEqual(result['lines'], [135])
        self.assertEqual([c.args[0] for c in machine._qtest.call_args_list],
                         ['set_irq_in /master input-event 135 1', 'set_irq_in /master input-event 135 0'])

    def test_whole_set_never_claims_verified_statistics_or_writes_memory(self):
        machine = self.machine()
        result = self.run_diagnostic(machine)
        self.assertTrue(result['diagnostic_only'])
        self.assertFalse(result['statistics_data_verified'])
        self.assertEqual(result['lines'], [3, 4, 96, 101, 135])
        self.assertEqual(machine._qtest.call_count, 10)
        self.assertTrue(all(c.args[0].startswith('set_irq_in /master input-event ') for c in machine._qtest.call_args_list))

    def test_disabled_metadata_engine_produces_no_event(self):
        machine = self.machine(masks={0x20069F00: 1})
        self.assertIsNone(metadata_route_diagnostic(machine))
        machine.qmp.command.assert_not_called()
        machine._qtest.assert_not_called()

    def test_metadata_diagnostic_requires_armed_irq_and_records_unverified_data(self):
        for mask, supplied in ((0, False), (0x40, True)):
            machine = self.machine(masks={0x20069F00: 0x11, 0x20068200: mask})
            with patch('probe_z62_liveview.master_event_path', return_value='/master'), \
                 patch('probe_z62_liveview.qtest_read', return_value=expected_raw_prefix()):
                result = metadata_route_diagnostic(machine)
            self.assertEqual(bool(result), supplied)
            if supplied:
                self.assertEqual(result['lines'], [6])
                self.assertFalse(result['statistics_data_verified'])
            self.assertEqual(machine._qtest.call_count, 2 if supplied else 0)


class DecompilationAuditTests(unittest.TestCase):
    def test_export_success_is_not_semantic_success(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            # Simulated tool output fixtures, not production code modifications.
            (path/'10239128.c').write_text('void callback(void) { halt_baddata(); }', encoding='utf-8')
            (path/'10239128.asm').write_text('10239128: push {r4,lr}', encoding='utf-8')
            result = audit_exports(path, [0x10239128])
            self.assertFalse(result['all_exports_structurally_usable'])
            self.assertFalse(result['semantics_verified'])
            self.assertIn('halt_baddata', result['issues'][0]['issue'])

    def test_missing_instruction_listing_is_incomplete(self):
        with tempfile.TemporaryDirectory() as folder:
            result = audit_exports(Path(folder), [0x10239128])
            self.assertFalse(result['all_exports_structurally_usable'])

    def test_bad_stack_analysis_is_not_silently_accepted(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            (path/'1022e15c.c').write_text('/* WARNING: Possible PIC construction */ BADSPACEBASE *x;', encoding='utf-8')
            (path/'1022e15c.asm').write_text('1022e15c: push {r4,lr}', encoding='utf-8')
            result = audit_exports(path, [0x1022e15c])
            self.assertFalse(result['all_exports_structurally_usable'])
            self.assertEqual(len(result['issues']), 2)


if __name__ == '__main__':
    unittest.main()
