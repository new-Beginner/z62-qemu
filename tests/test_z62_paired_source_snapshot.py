"""Read-only source packets must retain unknowns and independent layouts."""
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))


class Memory:
    def __init__(self):
        self.regions, self.reads = [], []

    def put(self, address, data):
        self.regions.append((address, data))

    def read(self, address, count):
        self.reads.append((address, count))
        for start, data in self.regions:
            if start <= address and address+count <= start+len(data):
                return data[address-start:address-start+count]
        raise ValueError('No test backing for requested read')


class PairedSourceSnapshotTests(unittest.TestCase):
    def api(self):
        try:
            import z62_paired_source_snapshot as module
        except ImportError as exc:
            self.fail('Original paired source capture is missing: '+str(exc))
        return module

    def fixture(self):
        memory = Memory()
        core = bytearray(68)
        struct.pack_into('<4H', core, 44, 0, 0, 1516, 854)
        source = bytearray(80)
        struct.pack_into('<4I', source, 12, 0x8448dc00, 0x85d1b800, 0x875a9400, 0x82c00000)
        struct.pack_into('<H', source, 76, 2288)
        roots = [0]*52
        roots[0], roots[3], roots[9] = 0xc2001000, 0xc2002000, 0
        memory.put(0xc2000000, struct.pack('<52I', *roots))
        memory.put(0xc2001000, bytes(core))
        memory.put(0xc2002000, bytes(source))
        memory.put(0xc2003000, b'\0\0\0\0\0\0\0\0')
        formatter = bytearray(52)
        struct.pack_into('<2I', formatter, 24, 1514 << 16, 1006 << 16)
        memory.put(0x20069500, bytes(formatter))
        memory.put(0x20069a08, struct.pack('<I', 2272))
        memory.put(0x20380048, struct.pack('<I', 0x05ea03ee))
        memory.put(0x2038030c, struct.pack('<I', 2272))
        return memory

    def test_dispatch_separates_new_packets_from_previous_mmio(self):
        module = self.api()
        row = module.dispatch(self.fixture(), 0xc2003000, 0xc2000000)
        self.assertEqual(row['core']['layout_argument'], [1516, 854])
        self.assertEqual(row['source']['stride_argument'], 2288)
        self.assertEqual(row['upstream_before']['layout_fields'], [1514, 1006, 2272])
        self.assertEqual(row['paired_before']['layout_fields'], [1514, 1006, 2272])
        self.assertIsNone(row['outputs']['raw'])
        self.assertFalse(row['configuration_has_already_been_written'])

    def test_missing_and_unbacked_packets_are_unknown_not_zero(self):
        module = self.api()
        memory = self.fixture()
        roots = [0]*52
        roots[3] = 0xc2004000
        memory.regions[0] = (0xc2000000, struct.pack('<52I', *roots))
        row = module.dispatch(memory, 0xc2003000, 0xc2000000)
        self.assertIsNone(row['core']['layout_argument'])
        self.assertIsNone(row['source']['stride_argument'])
        self.assertIn('error', row['source'])
        self.assertFalse(row['source']['captured'])

    def test_peripheral_pointer_is_never_dereferenced_as_packet(self):
        module = self.api()
        memory = self.fixture()
        roots = [0]*52
        roots[0] = 0xf8f01000
        memory.regions[0] = (0xc2000000, struct.pack('<52I', *roots))
        row = module.dispatch(memory, 0xc2003000, 0xc2000000)
        self.assertFalse(row['core']['captured'])
        self.assertFalse(any(address == 0xf8f01000 for address, _ in memory.reads))

    def test_format_return_reads_actual_committed_values(self):
        module = self.api()
        memory = self.fixture()
        row = module.format_packet(memory, 0xc2003000, 0xc200102c, after=False)
        self.assertEqual(row['core']['layout_argument'], [1516, 854])
        self.assertEqual(row['paired_observed']['layout_fields'], [1514, 1006, 2272])
        memory.regions[-2] = (0x20380048, struct.pack('<I', 0x05ec0356))
        returned = module.format_packet(memory, 0xc2003000, 0xc200102c, after=True)
        self.assertEqual(returned['paired_observed']['layout_fields'], [1516, 854, 2272])
        self.assertTrue(returned['geometry_argument_matches_observed'])
        self.assertEqual(returned['paired_observed']['layout_fields'][-1], 2272)

    def test_source_coverage_requires_real_packets_in_every_phase(self):
        from trace_z62_paired_source import coverage
        module = self.api()
        rows = [{'selector_phase': phase,
                 'snapshot': module.dispatch(self.fixture(), 0xc2003000, 0xc2000000)}
                for phase in (0, 1, 2)]
        self.assertEqual(coverage(rows), [0, 1, 2])
        rows[-1]['snapshot']['source']['captured'] = False
        self.assertEqual(coverage(rows), [0, 1])
        rows[-1]['snapshot']['source']['captured'] = True
        rows[-1]['snapshot']['bank_byte4'] = 1
        self.assertEqual(coverage(rows), [0, 1])

    def test_pairing_checks_real_stack_delta_and_preserved_source(self):
        from trace_z62_paired_source import correlate
        entry = {'thread': '02', 'registers': {'sp': 0xc5417000, 'r0': 0xc2003000,
                  'r1': 0xc200102c}, 'snapshot': {'kind': 'geometry-entry'}}
        returned = {'thread': '02', 'registers': {'sp': 0xc5416ff0, 'r5': 0xc2003000,
                     'r6': 0xc200102c}, 'snapshot': {'kind': 'geometry-written'}}
        self.assertEqual(len(correlate([entry, returned])['pairs']), 1)
        returned['registers']['r6'] += 4
        invalid = correlate([entry, returned])
        self.assertEqual(len(invalid['pairs']), 0)
        self.assertEqual(len(invalid['incomplete']), 1)
        self.assertEqual(len(correlate([returned])['unmatched_returns']), 1)

