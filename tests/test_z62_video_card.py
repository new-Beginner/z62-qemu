"""One card stores real photos and finalized silent movies transactionally."""
from copy import deepcopy
from importlib.util import find_spec
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from z62_media_card import MediaCard
from z62_video_codec import VideoRecorder
from test_z62_video_codec import frame


@unittest.skipUnless(find_spec('av'), 'Optional video profile: use .build/tools/video-r26/Scripts/python.exe')
class VideoCardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as directory:
            recorder = VideoRecorder(Path(directory), start_ns=0, clock_epoch='video-test')
            try:
                recorder.append(frame('red', 10_000_000, 1))
                recorder.append(frame('blue', 70_000_000, 2))
                cls.movie = recorder.finish(100_000_000)
            finally:
                recorder.abort()

    def setUp(self):
        try:
            import z62_video_card as card
        except ImportError as exc:
            self.fail('The photo/video card is missing: ' + str(exc))
        self.api = card
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.card = card.VideoCard.create(self.root / 'card')
        self.addCleanup(self.card.close)

    def store(self):
        return self.card.store_video(**self.movie)

    def test_photo_and_movie_share_numbers_and_survive_reopen(self):
        self.card.store_jpeg(self.movie['poster'], {'implementation_level': 'C', 'width': 64, 'height': 64})
        saved = self.store()
        self.assertEqual(saved['name'], 'Z62_0002.MP4')
        self.assertEqual(saved['kind'], 'video')
        self.assertEqual(saved['poster'], 'Z62_0002.JPG')
        self.assertEqual(len(self.card.list()), 2)
        self.card.close()
        with self.api.VideoCard(self.root / 'card') as reopened:
            self.assertEqual([row['kind'] for row in reopened.list()], ['photo', 'video'])
            self.assertEqual(reopened.read('Z62_0002.MP4'), self.movie['video'])
            self.assertEqual(reopened.read('Z62_0002.JPG'), self.movie['poster'])

    def test_movie_delete_removes_its_poster_without_reusing_the_number(self):
        self.store()
        self.card.delete('Z62_0001.JPG')
        self.assertEqual(self.card.list(), [])
        self.assertEqual(list(self.card.image_directory.iterdir()), [])
        self.assertEqual(self.store()['name'], 'Z62_0002.MP4')

    def test_capacity_counts_movie_and_poster_before_publication(self):
        small = self.api.VideoCard.create(self.root / 'small',
            capacity_bytes=len(self.movie['video']) + len(self.movie['poster']) - 1)
        self.addCleanup(small.close)
        with self.assertRaisesRegex(ValueError, 'card_full'):
            small.store_video(**self.movie)
        self.assertEqual(small.list(), [])
        self.assertEqual(list(small.image_directory.iterdir()), [])

    def test_failed_commit_does_not_publish_a_movie_or_consume_its_number(self):
        with patch.object(self.api.os, 'replace', side_effect=OSError('simulated video catalog failure')):
            with self.assertRaisesRegex(OSError, 'video catalog failure'):
                self.store()
        self.assertEqual(self.card.list(), [])
        self.assertEqual(list(self.card.image_directory.iterdir()), [])
        self.assertEqual(self.store()['name'], 'Z62_0001.MP4')

    def test_metadata_cannot_claim_other_frame_pixels_or_timestamps(self):
        for field, value in (('pixel_sha256', '0' * 64), ('virtual_time_ns', 30_000_000)):
            metadata = deepcopy(self.movie['metadata'])
            metadata['samples'][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.card.store_video(video=self.movie['video'], poster=self.movie['poster'], metadata=metadata)
        self.assertEqual(self.card.list(), [])

    def test_existing_v2_card_is_not_silently_upgraded(self):
        old = MediaCard.create(self.root / 'old')
        old.close()
        before = (self.root / 'old/.z62-camera.json').read_bytes()
        with self.assertRaises(ValueError):
            self.api.VideoCard(self.root / 'old')
        self.assertEqual((self.root / 'old/.z62-camera.json').read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
