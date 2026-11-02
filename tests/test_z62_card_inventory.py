"""Bounded parser checks on newly created synthetic virtual-card fixtures."""
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from z62_virtual_sd import create_fat32
from inspect_z62_virtual_card import Fat32, inspect


class CardInventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.card = Path(self.temp.name)/'card.raw'
        geometry = create_fat32(self.card, 512)
        self.fat = (2048+32)*512
        self.root = (2048+32+2*geometry['fat_sectors'])*512
        self.cluster_bytes = geometry['sectors_per_cluster']*512

    def write(self, offset, data):
        with self.card.open('r+b') as stream:
            stream.seek(offset)
            stream.write(data)

    def test_blank_volume_is_empty_and_reader_never_claims_photo_success(self):
        before = self.card.stat().st_mtime_ns
        result = inspect(self.card)
        self.assertEqual(result['files'], [])
        self.assertTrue(result['read_only'])
        self.assertFalse(result['photo_saved_verified'])
        self.assertEqual(self.card.stat().st_mtime_ns, before)

    def test_signature_is_only_a_hint_not_a_valid_encoded_photo(self):
        entry = bytearray(32)
        entry[:11] = b'DSC_0001JPG'
        entry[11] = 0x20
        struct.pack_into('<HI', entry, 26, 3, 8)
        self.write(self.root, entry+b'\0'*32)
        self.write(self.fat+12, struct.pack('<I', 0x0fffffff))
        self.write(self.root+self.cluster_bytes, b'\xff\xd8\xffFAKE!')
        result = inspect(self.card)
        self.assertEqual(result['files'][0]['format_hint'], 'JPEG')
        self.assertFalse(result['photo_saved_verified'])

    def test_cluster_cycle_is_bounded(self):
        self.write(self.root, b'\xe5'*self.cluster_bytes)
        self.write(self.fat+8, struct.pack('<I', 2))
        with self.assertRaisesRegex(ValueError, 'cycle'):
            inspect(self.card)

    def test_partition_cannot_escape_regular_file(self):
        self.write(446+12, struct.pack('<I', 0xffffffff))
        with self.assertRaisesRegex(ValueError, 'Partition exceeds'):
            inspect(self.card)


if __name__ == '__main__':
    unittest.main()
