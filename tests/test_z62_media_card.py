"""One committed photo may own JPEG and NEF; neither may be half-published."""
from io import BytesIO
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
import unittest

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from z62_nef_codec import encode_nef


class MediaCardTests(unittest.TestCase):
    def setUp(self):
        try:
            import z62_media_card as card
        except ImportError as exc:
            self.fail('The grouped-media card is missing: ' + str(exc))
        self.api = card
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.card = card.MediaCard.create(self.root / 'card')
        self.addCleanup(self.card.close)
        image = Image.new('RGB', (64, 64), 'red')
        output = BytesIO()
        image.save(output, format='JPEG')
        self.jpeg = output.getvalue()
        self.metadata = {'implementation_level': 'C', 'width': 64, 'height': 64, 'frame_id': 3}
        self.nef = encode_nef(np.full((104, 160), 2048, dtype=np.uint16), image, self.metadata)

    def test_pair_is_one_photo_and_reopens_with_both_unchanged_files(self):
        saved = self.card.store_photo(jpeg=self.jpeg, nef=self.nef, metadata=self.metadata)
        self.assertEqual(saved['name'], 'Z62_0001.JPG')
        self.assertEqual([f['name'] for f in saved['files']], ['Z62_0001.JPG', 'Z62_0001.NEF'])
        self.assertEqual(len(self.card.list()), 1)
        self.assertEqual(self.card.summary()['used_payload_bytes'], len(self.jpeg) + len(self.nef))
        self.card.close()
        with self.api.MediaCard(self.root / 'card') as reopened:
            self.assertEqual(reopened.read('Z62_0001.JPG'), self.jpeg)
            self.assertEqual(reopened.read('Z62_0001.NEF'), self.nef)

    def test_nef_only_is_a_real_primary_file(self):
        saved = self.card.store_photo(jpeg=None, nef=self.nef, metadata=self.metadata)
        self.assertEqual(saved['name'], 'Z62_0001.NEF')
        self.assertEqual(self.card.read(saved['name']), self.nef)
        self.assertEqual(self.card.item(saved['name'])['kind'], 'photo')

    def test_delete_removes_the_whole_pair_without_reusing_its_number(self):
        self.card.store_photo(jpeg=self.jpeg, nef=self.nef, metadata=self.metadata)
        self.card.delete('Z62_0001.JPG')
        self.assertEqual(self.card.list(), [])
        self.assertEqual(list(self.card.image_directory.iterdir()), [])
        saved = self.card.store_photo(jpeg=self.jpeg, nef=None, metadata=self.metadata)
        self.assertEqual(saved['name'], 'Z62_0002.JPG')

    def test_capacity_counts_both_members_before_writing(self):
        small = self.api.MediaCard.create(self.root / 'small', capacity_bytes=len(self.jpeg) + len(self.nef) - 1)
        self.addCleanup(small.close)
        with self.assertRaisesRegex(ValueError, 'card_full'):
            small.store_photo(jpeg=self.jpeg, nef=self.nef, metadata=self.metadata)
        self.assertEqual(small.list(), [])
        self.assertEqual(list(small.image_directory.iterdir()), [])

    def test_failed_commit_does_not_leave_a_visible_half_pair(self):
        with patch.object(self.api.os, 'replace', side_effect=OSError('simulated catalog failure')):
            with self.assertRaises(OSError):
                self.card.store_photo(jpeg=self.jpeg, nef=self.nef, metadata=self.metadata)
        self.assertEqual(self.card.list(), [])
        self.assertEqual(list(self.card.image_directory.iterdir()), [])

    def test_failed_group_delete_restores_both_files_and_the_committed_catalog(self):
        saved = self.card.store_photo(jpeg=self.jpeg, nef=self.nef, metadata=self.metadata)
        catalog = (self.card.root / '.z62-camera.json').read_bytes()
        replace = self.api.os.replace
        for failure_at in ('second-member', 'catalog'):
            with self.subTest(failure_at=failure_at):
                def fail_selected_move(source, destination):
                    if ((failure_at == 'second-member' and Path(source).name == 'Z62_0001.NEF') or
                            (failure_at == 'catalog' and Path(destination).name == '.z62-camera.json')):
                        raise OSError('simulated group deletion failure')
                    return replace(source, destination)

                with patch.object(self.api.os, 'replace', side_effect=fail_selected_move):
                    with self.assertRaisesRegex(OSError, 'group deletion failure'):
                        self.card.delete('Z62_0001.JPG')
                self.assertEqual(self.card.list(), [saved])
                self.assertEqual(self.card.read('Z62_0001.JPG'), self.jpeg)
                self.assertEqual(self.card.read('Z62_0001.NEF'), self.nef)
                self.assertEqual((self.card.root / '.z62-camera.json').read_bytes(), catalog)
                self.assertEqual(list(self.card.root.glob('.deleting-*')), [])
        self.card.close()
        with self.api.MediaCard(self.root / 'card') as reopened:
            self.assertEqual(reopened.list(), [saved])
            self.assertEqual(reopened.read('Z62_0001.NEF'), self.nef)

    def test_legacy_or_foreign_directories_are_not_upgraded_or_overwritten(self):
        from z62_directory_card import DirectoryCard
        old = DirectoryCard.create(self.root / 'legacy')
        old.close()
        with self.assertRaises(ValueError):
            self.api.MediaCard(self.root / 'legacy')
        with self.assertRaises(ValueError):
            self.api.MediaCard.create(self.root / 'legacy')

    def test_member_hash_and_path_checks_are_preserved(self):
        self.card.store_photo(jpeg=self.jpeg, nef=self.nef, metadata=self.metadata)
        (self.card.image_directory / 'Z62_0001.NEF').write_bytes(b'changed externally')
        with self.assertRaisesRegex(ValueError, 'corrupt'):
            self.card.read('Z62_0001.NEF')
        with self.assertRaises(ValueError):
            self.card.read('../../unrelated.txt')


if __name__ == '__main__':
    unittest.main()
