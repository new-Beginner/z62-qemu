"""Offline tests only; never import camera/USB or authorization tools."""
import copy
import importlib.util
import json
from pathlib import Path
import struct
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('z62_catalog', ROOT / 'tools/analyze_z62_ptp_catalog.py')
catalog = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(catalog)


class CatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = catalog.pinned_read(catalog.FIRMWARE, catalog.FIRMWARE_SHA256)
        cls.document = json.loads(catalog.pinned_read(catalog.DEVICE_INFO, catalog.DEVICE_SHA256))
        cls.result = catalog.analyze(cls.data, cls.document)

    def test_input_hash_and_size(self):
        self.assertEqual(len(self.data), 38750138)
        fake = Mock(name='input')
        fake.read_bytes.return_value = b'wrong image'
        with self.assertRaisesRegex(ValueError, 'SHA256 mismatch'):
            catalog.pinned_read(fake, catalog.FIRMWARE_SHA256)

    def test_namespaces_are_independent(self):
        caps = self.result['capabilities']
        self.assertEqual([len(caps[x]) for x in ('operations', 'events', 'properties')], [97, 27, 21])
        self.assertIn('0xC101', caps['events'])
        self.assertNotIn('0xC101', caps['operations'])
        self.assertIn('0x5001', caps['properties'])
        self.assertNotIn('0x5001', caps['operations'])
        self.assertEqual({x['code'] for x in self.result['namespace_collisions']}, {'0xC101', '0xC102'})

    def test_duplicate_capability_rejected(self):
        doc = copy.deepcopy(self.document)
        doc['device_info']['operations_supported'].append('0x1001')
        with self.assertRaisesRegex(ValueError, 'Invalid capability'):
            catalog.capabilities(doc)

    def test_all_97_have_unique_table_records(self):
        mapping = self.result['advertised_operation_mapping']
        self.assertEqual(len(mapping), 97)
        self.assertTrue(all(len(item['matches']) == 1 for item in mapping))
        self.assertEqual([sum(m['matches'][0]['table'] == name for m in mapping)
                          for name in ('standard', 'vendor', 'vendor_95xx')], [17, 68, 12])

    def test_table_counts_and_sentinels(self):
        self.assertEqual([t['record_count'] for t in self.result['tables']], [19, 70, 12, 175])
        self.assertEqual(self.result['counts']['records'], 276)
        for table in self.result['tables']:
            self.assertEqual(catalog.words(self.data, int(table['sentinel'], 16), 7), (0,) * 7)

    def test_corrupt_sentinel_and_literal_rejected(self):
        for address, message in ((0x119F1FA4, 'sentinel'), (0x1047B8F4, 'literal')):
            changed = bytearray(self.data)
            struct.pack_into('<I', changed, address - catalog.BASE, 123)
            with self.assertRaisesRegex(ValueError, message):
                catalog.parse_table(changed, *catalog.TABLES[0])

    def test_anchor_and_thumb_addresses(self):
        rows = self.result['tables'][3]['records'][-4:]
        self.assertEqual([r['operation'] for r in rows], ['0xC051', '0xC052', '0xC101', '0xC102'])
        self.assertEqual(rows[0]['record_address'], '0x119F5C20')
        self.assertEqual(rows[2]['handler_14'], '0x10779423')
        self.assertEqual(rows[2]['handler_code_address'], '0x10779422')

    def test_ram_context_not_forced_zero(self):
        rows = {r['operation']: r for r in self.result['tables'][0]['records']}
        self.assertEqual(rows['0x1014']['context_08'], '0xC188B76C')
        self.assertEqual(rows['0x1015']['context_08'], '0xC188B770')
        self.assertEqual(rows['0x1014']['handler_code_address'], '0x105043BE')

    def test_direct_calls_and_table_literals(self):
        evidence = self.result['xref_evidence']
        edges = {(x['site'], x['target']) for x in evidence['direct_edges_in_windows']}
        self.assertTrue({('0x104666C4', '0x1047B822'), ('0x104668CC', '0x1047B8D6'),
                         ('0x104C9706', '0x104C95EA'), ('0x104C9832', '0x104C95A8'),
                         ('0x10504350', '0x104CAD92'), ('0x10504354', '0x104CAD78')} <= edges)
        refs = {(x['pool'], x['value']) for x in evidence['pc_relative_literals']}
        for _, base, _, literal in catalog.TABLES:
            self.assertIn((catalog.hx(literal), catalog.hx(base)), refs)

    def test_indirect_calls_remain_unverified(self):
        sites = self.result['xref_evidence']['indirect_call_sites']
        self.assertTrue(all(not x['runtime_target_verified'] for x in sites))
        self.assertTrue({'0x1047B87E', '0x1047B8DC', '0x104C95F0', '0x105043E8'}
                        <= {x['site'] for x in sites})
        self.assertFalse(self.result['scope']['hardware_validation'])
        self.assertFalse(self.result['scope']['safety_certified'])

    def test_unrelated_equal_integer_does_not_create_operation(self):
        changed = bytearray(self.data)
        struct.pack_into('<I', changed, 0, 0xC105)
        again = catalog.analyze(changed, self.document)
        self.assertEqual(again['advertised_operation_mapping'], self.result['advertised_operation_mapping'])
        self.assertEqual(again['tables'], self.result['tables'])

    def test_address_bounds(self):
        for address in (catalog.BASE - 4, catalog.BASE + len(self.data)):
            with self.assertRaisesRegex(ValueError, 'outside'):
                catalog.words(self.data, address)


if __name__ == '__main__':
    unittest.main()
