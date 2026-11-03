"""Original descriptor fields and the complete root tail remain distinct."""
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from test_z62_paired_source_snapshot import Memory


class FrameSourceSnapshotTests(unittest.TestCase):
    def api(self):
        try:
            import z62_frame_source_snapshot as module
        except ImportError as exc:
            self.fail('Original frame source capture is missing: '+str(exc))
        return module

    def fixture(self):
        memory = Memory()
        context = bytearray(0x388)
        struct.pack_into('<3I', context, 4, 2, 0xc2005000, 0xc2005040)
        struct.pack_into('<I', context, 0x35c, 0xc2006000)
        memory.put(0xc2004000, bytes(context))
        for i in range(2):
            descriptor = bytearray(64)
            descriptor[0x24] = 2
            struct.pack_into('<3H', descriptor, 0x26, 2288, 1516, 854)
            struct.pack_into('<I', descriptor, 0x34, (0x8448dc00, 0x85d1b800)[i])
            memory.put(0xc2005000+i*64, bytes(descriptor))
        core = bytearray(68)
        struct.pack_into('<2H', core, 0x30, 1516, 854)
        memory.put(0xc2006000, bytes(core))
        roots = [0]*53
        roots[0], roots[3], roots[51], roots[52] = 0xc2006000, 0xc2007000, 0, 1
        memory.put(0xc2008000, struct.pack('<53I', *roots))
        source = bytearray(80)
        struct.pack_into('<H', source, 0x4c, 2288)
        memory.put(0xc2007000, bytes(source))
        return memory

    def test_records_descriptor_geometry_and_dma_without_assuming_freshness(self):
        row = self.api().capture(self.fixture(), 0xc2004000, 0xc2008000, after=False)
        self.assertEqual(row['descriptor_count'], 2)
        self.assertEqual(row['descriptors'][0]['layout_fields'], [1516, 854, 2288])
        self.assertEqual(row['descriptors'][0]['dma_address'], '0x8448dc00')
        self.assertEqual(row['template_core']['layout_argument'], [1516, 854])
        self.assertTrue(row['all_source_descriptors_captured'])
        self.assertFalse(row['actual_pixel_production_verified'])
        self.assertIsNone(row['serialized_root'])

    def test_return_captures_word52_and_serialized_source(self):
        row = self.api().capture(self.fixture(), 0xc2004000, 0xc2008000, after=True)
        self.assertEqual(row['serialized_root']['requested_bytes'], 212)
        self.assertEqual(row['serialized_root_flags'], {'word51_cc': 0, 'word52_d0': 1})
        self.assertEqual(row['serialized_source']['stride_argument'], 2288)
        self.assertTrue(row['template_matches_serialized_geometry'])

    def test_bad_count_does_not_read_a_fifth_descriptor(self):
        module = self.api()
        memory = self.fixture()
        context = bytearray(memory.regions[0][1])
        struct.pack_into('<I', context, 4, 5)
        memory.regions[0] = (0xc2004000, bytes(context))
        row = module.capture(memory, 0xc2004000, 0xc2008000, after=False)
        self.assertFalse(row['descriptor_count_supported'])
        self.assertEqual(row['descriptors'], [])
        self.assertFalse(row['all_source_descriptors_captured'])

    def test_missing_or_peripheral_descriptor_stays_unknown(self):
        module = self.api()
        memory = self.fixture()
        context = bytearray(memory.regions[0][1])
        struct.pack_into('<I', context, 8, 0xf8f01000)
        memory.regions[0] = (0xc2004000, bytes(context))
        row = module.capture(memory, 0xc2004000, 0xc2008000, after=False)
        self.assertIsNone(row['descriptors'][0]['layout_fields'])
        self.assertFalse(row['all_source_descriptors_captured'])
        self.assertFalse(any(address == 0xf8f01000 for address, _ in memory.reads))

    def test_constructor_pairing_respects_postincremented_root_register(self):
        from trace_z62_frame_source import correlate
        entry = {'pc': 0x102c1e1e, 'thread': '02', 'registers':
                 {'sp': 0xc5417000, 'r0': 0xc2004000, 'r1': 0xc2008000}}
        returned = {'pc': 0x102c1ea2, 'thread': '02', 'registers':
                    {'sp': 0xc5416ff0, 'r5': 0xc2004000, 'r4': 0xc20080cc}}
        self.assertEqual(len(correlate([entry, returned])['pairs']), 1)
        returned['registers']['r4'] -= 0xcc
        bad = correlate([entry, returned])
        self.assertEqual(len(bad['pairs']), 0)
        self.assertEqual(len(bad['incomplete']), 1)

