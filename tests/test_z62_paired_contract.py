"""Separate programmed layouts, alias rings, inactive WORK and actual pixels."""
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))


class PairedContractTests(unittest.TestCase):
    def api(self):
        try:
            import inspect_z62_paired_contract
        except ImportError as exc:
            self.fail('Paired layout inspector is missing: '+str(exc))
        return inspect_z62_paired_contract

    def fixture(self, *, work=True, shared=False):
        data = bytearray(0x800)
        def word(offset, value):
            struct.pack_into('<I', data, offset, value)
        for offset, value in ((0x48, 0x05ec0356), (0x30c, 2288),
                (0x408, int(work)), (0x410, int(work)), (0x420, 1), (0x428, 1),
                (0x424, 3 if shared else 0), (0x470, 1520), (0x4c8, 1520)):
            word(offset, value)
        for i, value in enumerate((0x8448dc00, 0x85d1b800, 0x875a9400, 0x82c00000)):
            word(0x310+i*4, value)
        for i in range(4):
            y = 0x40000000 if shared else (0xedb82c00, 0xef5a6a00)[i % 2]
            uv = 0x40008000 if shared else y+1285920
            for first, second in ((0x488, 0x498), (0x4a8, 0x4b8)):
                word(first+i*4, y); word(second+i*4, uv)
            for first, second in ((0x430, 0x440), (0x450, 0x460)):
                base = (0xf0fca800, 0xf11f7c00)[i % 2]
                word(first+i*4, base); word(second+i*4, base+642960)
        ports = [{'index': i, 'words': [0]*13} for i in range(16)]
        ports[8]['words'] = [0x09000201, 0, 0, 0, 1520, 1520, 0, 0, 0x034e05e4, 0, 1285920, 0, 0]
        return {'paired_raw_800': data.hex(), 'ports': ports,
            'raw': {'width_field_high16': 1514, 'height_field_high16': 1006,
                    'dma_fields': {'0x8': 2272},
                    'selected_destinations': [hex(v) for v in (0x82c00000, 0x8448dc00, 0x85d1b800, 0x875a9400)]}}

    def test_same_addresses_do_not_erase_different_source_layouts(self):
        row = self.api().decode(self.fixture())
        self.assertEqual(row['paired_source']['layout_fields'], [1516, 854, 2288])
        self.assertEqual(row['upstream_raw']['layout_fields'], [1514, 1006, 2272])
        self.assertTrue(row['source_address_sets_equal'])
        self.assertFalse(row['source_layouts_equal'])
        self.assertFalse(row['actual_pixel_production_verified'])

    def test_two_alias_units_are_not_four_independent_frames(self):
        row = self.api().decode(self.fixture())
        self.assertEqual(row['main']['slot_layout_fields'], [1508, 846, 1520])
        self.assertEqual(row['main']['unique_first_ring_pairs'], 2)
        self.assertTrue(row['main']['second_ring_matches_first'])
        self.assertTrue(row['main']['all_uv_deltas_match_slot'])
        self.assertEqual(row['work']['unique_first_ring_pairs'], 2)
        self.assertEqual(row['work']['first_ring'][0]['plane_delta'], 642960)

    def test_disabled_work_retains_registers_without_becoming_active(self):
        row = self.api().decode(self.fixture(work=False, shared=True))
        self.assertEqual(row['main']['address_kind'], 'shared-port')
        self.assertFalse(row['work']['enabled'])
        self.assertTrue(row['work']['registers_retained'])
        self.assertFalse(row['work']['active_history_verified'])
        self.assertFalse(row['main']['all_uv_deltas_match_slot'])

    def test_short_capture_and_disagreeing_enable_pair_remain_errors(self):
        module = self.api()
        short = self.fixture()
        short['paired_raw_800'] = short['paired_raw_800'][:0x440*2]
        with self.assertRaisesRegex(ValueError, '0x800'):
            module.decode(short)
        changed = self.fixture()
        data = bytearray.fromhex(changed['paired_raw_800'])
        struct.pack_into('<I', data, 0x410, 0)
        changed['paired_raw_800'] = data.hex()
        with self.assertRaisesRegex(ValueError, 'WORK'):
            module.decode(changed)

