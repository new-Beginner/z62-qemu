"""Virtual media under the current workspace entry's Path adaptation.

Actual card IO, transactions and rejections remain active; no physical media.
"""
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from z62_virtual_sd import CardSession, create_fat32, image_path
import z62_virtual_sd as virtual_sd
import z62_workspace_paths as storage


class VirtualSDTests(unittest.TestCase):
    def setUp(self):
        path_type=Path if str(storage.ROOT).isascii() else storage.WorkspacePath
        transport=patch.object(virtual_sd,'Path',path_type)
        transport.start(); self.addCleanup(transport.stop)
        self.temp = tempfile.TemporaryDirectory(dir=os.environ.get('PI_SCRATCH_DIR'))
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.image = self.root / '中文卡.img'
        self.image.write_bytes(b'A' * 1024)
        self.work = self.root / 'stage'
        self.work.mkdir()

    def card(self, mode='snapshot'):
        card = CardSession(self.image, self.work, mode)
        self.addCleanup(card.close)
        return card

    def test_snapshot_never_commits(self):
        card = self.card()
        card.staged.write_bytes(b'B' * 1024)
        self.assertFalse(card.commit())
        self.assertEqual(self.image.read_bytes(), b'A' * 1024)

    def test_persistent_saves_and_reopens(self):
        card = self.card('persistent')
        card.staged.write_bytes(b'B' * 1024)
        self.assertTrue(card.commit())
        self.assertTrue(card.record()['saved'])
        card.close()
        self.assertFalse(card.lock.exists())
        self.assertEqual(self.image.read_bytes(), b'B' * 1024)
        with self.assertRaises(ValueError):
            card.commit()
        second = self.root / 'second'
        second.mkdir()
        with_card = CardSession(self.image, second, 'persistent')
        self.addCleanup(with_card.close)
        self.assertEqual(with_card.staged.read_bytes(), b'B' * 1024)

    def test_concurrent_writer_rejected(self):
        card = self.card('persistent')
        second = self.root / 'second'
        second.mkdir()
        with self.assertRaises(FileExistsError):
            CardSession(self.image, second, 'persistent')
        self.assertTrue(card.lock.exists())

    def test_external_modification_preserved(self):
        card = self.card('persistent')
        card.staged.write_bytes(b'B' * 1024)
        self.image.write_bytes(b'C' * 1024)
        with self.assertRaisesRegex(ValueError, 'externally'):
            card.commit()
        self.assertEqual(self.image.read_bytes(), b'C' * 1024)
        self.assertEqual(card.staged.read_bytes(), b'B' * 1024)

    def test_wrong_size_rejected(self):
        card = self.card('persistent')
        card.staged.write_bytes(b'B' * 512)
        with self.assertRaisesRegex(ValueError, 'size'):
            card.commit()
        self.assertEqual(self.image.read_bytes(), b'A' * 1024)

    def test_close_without_commit_does_not_save(self):
        card = self.card('persistent')
        card.staged.write_bytes(b'B' * 1024)
        card.close()
        self.assertEqual(self.image.read_bytes(), b'A' * 1024)
        self.assertTrue(card.staged.exists())

    def test_bad_paths_and_modes(self):
        for path in (self.root, self.root / 'firmware.bin'):
            with self.assertRaises(ValueError):
                image_path(path)
        invalid = self.root / 'bad.img'
        for content in (b'', b'x' * 513):
            invalid.write_bytes(content)
            with self.assertRaises(ValueError):
                image_path(invalid)
        with self.assertRaises(ValueError):
            CardSession(self.image, self.work, 'invalid')

    def test_exclusive_creation_and_invalid_size(self):
        with self.assertRaises(FileExistsError):
            create_fat32(self.image)
        self.assertEqual(self.image.read_bytes(), b'A' * 1024)
        for size in (0, 256, 513, True, 65536):
            with self.subTest(size=size), self.assertRaises(ValueError):
                create_fat32(self.root / 'new.img', size)
        self.assertFalse((self.root / 'new.img').exists())

    def test_fat32_geometry_and_backup(self):
        path = self.root / 'blank.raw'
        info = create_fat32(path)
        self.assertEqual(path.stat().st_size, 512 * 1024**2)
        with path.open('rb') as src:
            def sector(index):
                src.seek(index * 512)
                return src.read(512)
            mbr = sector(0)
            self.assertEqual(mbr[510:], b'\x55\xaa')
            self.assertEqual(mbr[450], 0x0c)
            start, length = struct.unpack_from('<II', mbr, 454)
            self.assertEqual(start + length, path.stat().st_size // 512)
            boot = sector(start)
            self.assertEqual(boot, sector(start + 6))
            self.assertEqual(boot[510:], b'\x55\xaa')
            self.assertEqual(struct.unpack_from('<H', boot, 11)[0], 512)
            self.assertEqual(boot[16], 2)
            self.assertEqual(struct.unpack_from('<I', boot, 32)[0], length)
            reserved = struct.unpack_from('<H', boot, 14)[0]
            fat = struct.unpack_from('<I', boot, 36)[0]
            count = (length - reserved - 2 * fat) // boot[13]
            self.assertGreaterEqual(count, 65525)
            self.assertGreaterEqual(fat * 128, count + 2)
            self.assertEqual(count, info['clusters'])
            self.assertEqual(sector(start + reserved), sector(start + reserved + fat))
            self.assertEqual(struct.unpack_from('<III', sector(start + reserved)),
                             (0x0ffffff8, 0xffffffff, 0x0fffffff))
            fsinfo = sector(start + 1)
            self.assertEqual(fsinfo, sector(start + 7))
            self.assertEqual(struct.unpack_from('<I', fsinfo, 488)[0], count - 1)
            root = sector(start + reserved + 2 * fat)
            self.assertEqual(root[:11], b'Z62 VIRTUAL')
            self.assertEqual(root[11], 8)


if __name__ == '__main__':
    unittest.main()
