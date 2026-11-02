"""Publication is distinct from native consumption; uncertain writes never replay."""
import base64
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from z62_scene_packet import parse_packet
from z62_software_camera import Frame


class Qmp:
    def __init__(self):
        self.current = {'epoch': 0, 'publish_id': 1, 'frame_id': 0, 'virtual_time_ns': 0}
        self.used = {'epoch': 0, 'publish_id': 0, 'frame_id': 0, 'virtual_time_ns': 0}
        self.writes = 0
        self.lose_reply = False
        self.last_file = None

    def command(self, name, args):
        if name == 'qom-set':
            if args['property'] == 'scene-file':
                self.last_file = Path(args['value'])
                packet = self.last_file.read_bytes()
            elif args['property'] == 'scene-packet':
                packet = base64.b64decode(args['value'])
            else:
                raise ValueError('Unexpected control operation')
            self.current, _ = parse_packet(packet)
            self.writes += 1
            if self.lose_reply:
                self.lose_reply = False
                raise TimeoutError('reply deadline, outcome unknown')
            return None
        if name != 'qom-get':
            raise ValueError('Unexpected monitor operation')
        prop = args['property']
        if prop == 'scene-publish-id':
            return self.current['publish_id']
        field = prop.removeprefix('scene-used-').replace('-', '_').replace('time_ns', 'virtual_time_ns')
        return self.used[field]


class SceneExchangeTests(unittest.TestCase):
    def setUp(self):
        try:
            from z62_scene_exchange import SceneExchange
        except ImportError as exc:
            self.fail('The acknowledged scene exchange is missing: ' + str(exc))
        self.qmp = Qmp()
        self.exchange = SceneExchange(self.qmp, epoch=0x62)

    def frame(self, ns=0, revision=0):
        return Frame(Image.new('RGB', (64, 64), (255, 0, 0)),
                     {'implementation_level': 'C', 'width': 64, 'height': 64,
                      'frame_id': ns * 30 // 1_000_000_000, 'virtual_time_ns': ns,
                      'scene_revision': revision})

    def test_published_frame_is_unavailable_until_native_dma_consumes_it(self):
        self.exchange.publish(self.frame())
        with self.assertRaisesRegex(ValueError, 'scene_not_consumed'):
            self.exchange.capture_frame(0, 0)
        self.qmp.used = deepcopy(self.qmp.current)
        captured = self.exchange.capture_frame(20_000_000, 0)
        self.assertEqual(captured.metadata['frame_id'], 0)
        self.assertEqual(captured.metadata['capture_virtual_time_ns'], 20_000_000)
        self.assertEqual(captured.metadata['native_scene_source']['publish_id'], 2)
        self.assertEqual(captured.image.getpixel((0, 0)), (255, 0, 0))

    def test_changed_settings_require_a_matching_consumed_revision(self):
        self.exchange.publish(self.frame())
        self.qmp.used = deepcopy(self.qmp.current)
        self.exchange.observe()
        self.exchange.publish(self.frame(100_000_000, 1))
        with self.assertRaisesRegex(ValueError, 'scene_settings_pending'):
            self.exchange.capture_frame(110_000_000, 1)
        self.qmp.used = deepcopy(self.qmp.current)
        self.assertEqual(self.exchange.capture_frame(120_000_000, 1).metadata['scene_revision'], 1)

    def test_lost_publish_reply_is_resolved_by_observation_without_replay(self):
        self.qmp.lose_reply = True
        self.exchange.publish(self.frame())
        self.assertTrue(self.exchange.state()['publish_outcome_unknown'])
        self.assertEqual(self.qmp.writes, 1)
        self.exchange.observe()
        self.assertFalse(self.exchange.state()['publish_outcome_unknown'])
        self.assertEqual(self.qmp.writes, 1)

    def test_old_or_future_input_is_not_labelled_as_a_current_capture(self):
        self.exchange.publish(self.frame(100_000_000))
        self.qmp.used = deepcopy(self.qmp.current)
        with self.assertRaisesRegex(ValueError, 'future_scene_frame'):
            self.exchange.capture_frame(0, 0)
        with self.assertRaisesRegex(ValueError, 'scene_stale'):
            self.exchange.capture_frame(2_000_000_000, 0)

    def test_file_mailbox_keeps_uncertain_input_until_readback_confirmation(self):
        from z62_scene_exchange import SceneExchange
        with tempfile.TemporaryDirectory() as folder:
            exchange = SceneExchange(self.qmp, epoch=0x62, directory=Path(folder) / 'mailbox')
            self.qmp.lose_reply = True
            exchange.publish(self.frame())
            self.assertTrue(self.qmp.last_file.is_file())
            self.assertEqual(self.qmp.writes, 1)
            exchange.observe()
            self.assertFalse(self.qmp.last_file.exists())
            self.assertEqual(self.qmp.writes, 1)
            self.assertEqual(exchange.state()['transport'], 'file-mailbox')

    def test_confirmed_file_publication_is_removed_without_accumulation(self):
        from z62_scene_exchange import SceneExchange
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder) / 'mailbox'
            exchange = SceneExchange(self.qmp, epoch=0x62, directory=directory)
            exchange.publish(self.frame())
            self.assertEqual(list(directory.iterdir()), [])
            self.assertEqual(self.qmp.current['publish_id'], 2)


if __name__ == '__main__':
    unittest.main()
