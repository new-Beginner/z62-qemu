"""Real MP4 timestamps and independently decoded acknowledged source pixels."""
from copy import deepcopy
import hashlib
from importlib.util import find_spec
from pathlib import Path
import sys
import tempfile
import unittest

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from z62_scene_packet import make_packet
from z62_software_camera import Frame


def frame(color, time_ns, publication):
    image = Image.new('RGB', (64, 64), color)
    frame_id = time_ns * 30 // 1_000_000_000
    packet = make_packet(image, epoch=62, publish_id=publication, frame_id=frame_id, virtual_time_ns=time_ns)
    return Frame(image, {'implementation_level': 'C', 'clock_epoch': 'video-test', 'width': 64, 'height': 64,
        'frame_id': frame_id, 'virtual_time_ns': time_ns,
        'pixel_sha256': hashlib.sha256(image.tobytes()).hexdigest(),
        'native_scene_source': {'epoch': 62, 'publish_id': publication, 'frame_id': frame_id,
                                'virtual_time_ns': time_ns, 'raw_sha256': packet[56:88].hex()}})


@unittest.skipUnless(find_spec('av'), 'Optional video profile: use .build/tools/video-r26/Scripts/python.exe')
class VideoCodecTests(unittest.TestCase):
    def setUp(self):
        try:
            import z62_video_codec as codec
        except ImportError as exc:
            self.fail('The real acknowledged-frame video codec is missing: ' + str(exc))
        self.codec = codec
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.recorder = codec.VideoRecorder(Path(self.temp.name), start_ns=0, clock_epoch='video-test')
        self.addCleanup(self.recorder.abort)

    def test_variable_guest_times_and_stop_duration_survive_independent_decode(self):
        frames = [frame('red', 10_000_000, 1), frame('green', 70_000_000, 2), frame('blue', 110_000_000, 3)]
        for source in frames:
            self.recorder.append(source)
        result = self.recorder.finish(145_000_000)
        self.assertEqual(result['video'][4:8], b'ftyp')
        audit = self.codec.audit_video(result['video'])
        self.assertEqual(audit['width'], 64)
        self.assertEqual(audit['height'], 64)
        self.assertEqual(audit['timestamps_us'], [0, 60000, 100000])
        self.assertEqual(audit['duration_us'], 135000)
        self.assertEqual(audit.get('pixel_format'), 'yuv420p')
        self.assertEqual([row['pixel_sha256'] for row in result['metadata']['samples']],
                         [f.metadata['pixel_sha256'] for f in frames])
        self.assertEqual(audit['pixel_sha256'], result['metadata']['encoded_pixel_sha256'])
        self.assertIn('source_mse', result['metadata']['independent_audit'])
        self.assertTrue(all(value < 10 for value in result['metadata']['independent_audit']['source_mse']))
        self.assertEqual([row['native_scene_source']['publish_id'] for row in result['metadata']['samples']], [1, 2, 3])
        self.assertFalse(result['metadata']['audio'])
        self.assertFalse(result['metadata']['factory_encoder'])

    def test_repeated_dma_publication_is_not_encoded_as_another_frame(self):
        first = frame('white', 10_000_000, 1)
        self.assertTrue(self.recorder.append(first))
        self.assertFalse(self.recorder.append(first))
        self.recorder.append(frame('black', 70_000_000, 2))
        result = self.recorder.finish(100_000_000)
        self.assertEqual(len(self.codec.audit_video(result['video'])['pixel_sha256']), 2)

    def test_prestart_frames_are_not_part_of_the_recording(self):
        self.recorder.abort()
        self.recorder = self.codec.VideoRecorder(Path(self.temp.name), start_ns=50_000_000, clock_epoch='video-test')
        self.addCleanup(self.recorder.abort)
        self.assertFalse(self.recorder.append(frame('red', 10_000_000, 1)))
        self.recorder.append(frame('green', 70_000_000, 2))
        self.recorder.append(frame('blue', 110_000_000, 3))
        result = self.recorder.finish(145_000_000)
        self.assertEqual(self.codec.audit_video(result['video'])['duration_us'], 75000)
        self.assertEqual(result['metadata']['start_request_ns'], 50_000_000)

    def test_stop_is_exclusive_when_it_coincides_with_the_last_source_sample(self):
        for source in (frame('red', 10_000_000, 1), frame('green', 70_000_000, 2),
                       frame('blue', 110_000_000, 3)):
            self.recorder.append(source)
        try:
            result = self.recorder.finish(110_000_000)
        except ValueError as exc:
            self.fail('A source sampled exactly at the exclusive stop must be omitted: ' + str(exc))
        audit = self.codec.audit_video(result['video'])
        self.assertEqual(audit['timestamps_us'], [0, 60000])
        self.assertEqual(audit['duration_us'], 100000)
        self.assertEqual(len(result['metadata']['samples']), 2)

    def test_bad_pixels_epoch_and_time_do_not_append(self):
        self.recorder.append(frame('red', 10_000_000, 1))
        for corruption in ('pixel', 'epoch', 'time'):
            source = frame('green', 70_000_000, 2)
            if corruption == 'pixel':
                source.image.putpixel((0, 0), (0, 0, 0))
            elif corruption == 'epoch':
                source.metadata['clock_epoch'] = 'another-VM'
            else:
                source = frame('green', 5_000_000, 2)
            with self.subTest(corruption=corruption), self.assertRaises(ValueError):
                self.recorder.append(source)
        self.assertEqual(self.recorder.status()['frames'], 1)

    def test_insufficient_frames_or_invalid_stop_never_return_a_video(self):
        with self.assertRaises(ValueError):
            self.recorder.finish(10_000_000)
        self.recorder.append(frame('red', 10_000_000, 1))
        with self.assertRaises(ValueError):
            self.recorder.finish(20_000_000)
        self.recorder.append(frame('blue', 70_000_000, 2))
        with self.assertRaises(ValueError):
            self.recorder.finish(60_000_000)

    def test_buffer_limit_and_abort_do_not_touch_other_files(self):
        unrelated = Path(self.temp.name) / 'keep.bin'
        unrelated.write_bytes(b'keep this')
        self.recorder.abort()
        self.recorder = self.codec.VideoRecorder(Path(self.temp.name), start_ns=0,
                                                 clock_epoch='video-test', max_frames=2)
        self.addCleanup(self.recorder.abort)
        self.recorder.append(frame('red', 10_000_000, 1))
        self.recorder.append(frame('green', 70_000_000, 2))
        with self.assertRaisesRegex(ValueError, 'limit'):
            self.recorder.append(frame('blue', 110_000_000, 3))
        self.recorder.abort()
        self.assertEqual(unrelated.read_bytes(), b'keep this')
        self.assertEqual([p.name for p in Path(self.temp.name).iterdir()], ['keep.bin'])


if __name__ == '__main__':
    unittest.main()
