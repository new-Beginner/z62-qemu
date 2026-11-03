"""Do not skip mismatches or force unsampled cleanup writes into the window."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))


class ControlPairTests(unittest.TestCase):
    def api(self):
        import z62_mmio_write_trace as module
        self.assertTrue(hasattr(module, 'pair_controls'), 'Trace/ring pairing is missing')
        return module

    def event(self, entry, address, value, cpu=0):
        return {'trace_entry': entry, 'address': address, 'value': value, 'cpu': cpu, 'size': 4,
                'board_view': 'master' if cpu in (0, 1) else 'slave' if cpu in (2, 3) else None}

    def ring(self):
        return {'master': [{'sequence': 1, 'address': '0x20068010', 'value': '0x10', 'cpu': 0},
                           {'sequence': 2, 'address': '0x2006800c', 'value': '0x10', 'cpu': 0}], 'slave': []}

    def test_preserves_trace_tail_as_unsampled_instead_of_declaring_it_empty(self):
        events = [self.event(10, 0x20068010, 16), self.event(20, 0x2006800c, 16), self.event(30, 0x20068100, 128)]
        row = self.api().pair_controls(events, self.ring())
        self.assertEqual([p['trace_entry'] for p in row['pairs']['master']], [10, 20])
        self.assertEqual([p['sequence'] for p in row['pairs']['master']], [1, 2])
        self.assertEqual(row['tail_after_last_ring_sample']['master'][0]['trace_entry'], 30)

    def test_mismatch_is_not_skipped_to_find_a_later_convenient_match(self):
        events = [self.event(10, 0x20068010, 16), self.event(20, 0x2006800c, 32), self.event(30, 0x2006800c, 16)]
        with self.assertRaises(ValueError): self.api().pair_controls(events, self.ring())

    def test_unknown_cpu_is_not_assigned_to_master(self):
        events = [self.event(1, 0x20068010, 16, -1), self.event(10, 0x20068010, 16), self.event(20, 0x2006800c, 16)]
        row = self.api().pair_controls(events, self.ring())
        self.assertEqual(row['unattributed_control_writes'][0]['trace_entry'], 1)
        self.assertEqual(len(row['pairs']['master']), 2)
