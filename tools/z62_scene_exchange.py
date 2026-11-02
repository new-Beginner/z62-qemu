"""Own external RGB frames until native four-slot DMA acknowledges their tags."""
import base64
from collections import OrderedDict
from copy import deepcopy
import hashlib
from pathlib import Path

try:
    from .z62_scene_packet import make_packet
    from .z62_software_camera import Frame, CameraError
    from .z62_directory_card import plain_path
except ImportError:
    from z62_scene_packet import make_packet
    from z62_software_camera import Frame, CameraError
    from z62_directory_card import plain_path


class SceneExchange:
    def __init__(self, qmp, *, epoch, path='/machine/master-input', max_age_ns=1_000_000_000, directory=None):
        self.qmp, self.epoch, self.path = qmp, epoch, path
        self.max_age_ns = max_age_ns
        self.frames = OrderedDict()
        self.sequence = None
        self.uncertain = None
        self.consumed = None
        self.last_error = None
        self.observation_gaps = 0
        self.directory = None
        self.files = {}
        if directory is not None:
            directory = plain_path(directory)
            if not str(directory).isascii():
                raise CameraError('scene_mailbox_requires_ascii_staging')
            plain_path(directory.parent, directory=True)
            directory.mkdir(exist_ok=False)
            self.directory = directory

    def _discard_file(self, identifier):
        item = self.files.get(identifier)
        if item is None:
            return
        path, expected = item
        if hashlib.sha256(plain_path(path, directory=False).read_bytes()).hexdigest() != expected:
            raise CameraError('scene_mailbox_modified')
        path.unlink()
        del self.files[identifier]

    def get(self, name):
        return self.qmp.command('qom-get', {'path': self.path, 'property': name})

    def observe(self):
        if self.uncertain is not None:
            active = self.get('scene-publish-id')
            if active == self.uncertain:
                self._discard_file(self.uncertain)
                self.uncertain = None
                self.last_error = None
            elif active > self.uncertain:
                raise CameraError('foreign_scene_publisher')
        first = self.get('scene-used-publish-id')
        if not first:
            return
        if self.consumed and self.consumed.metadata['native_scene_source']['publish_id'] == first:
            return
        tag = {'publish_id': first, 'epoch': self.get('scene-used-epoch'),
               'frame_id': self.get('scene-used-frame-id'),
               'virtual_time_ns': self.get('scene-used-time-ns')}
        if self.get('scene-used-publish-id') != first:
            self.observation_gaps += 1
            return
        frame = self.frames.get(first)
        if frame is None:
            self.consumed = None  # bootstrap/foreign pixels are not an owned RGB frame
            return
        expected = frame.metadata['native_scene_source']
        if any(expected[key] != value for key, value in tag.items()):
            raise CameraError('native_scene_tag_mismatch')
        self.consumed = frame

    def publish(self, frame):
        self.observe()
        if self.uncertain is not None:
            return False
        if self.sequence is None:
            self.sequence = self.get('scene-publish-id')
        self.sequence += 1
        identifier = self.sequence
        data = make_packet(frame.image, epoch=self.epoch, publish_id=identifier,
                           frame_id=frame.metadata['frame_id'],
                           virtual_time_ns=frame.metadata['virtual_time_ns'])
        metadata = deepcopy(frame.metadata)
        metadata['native_scene_source'] = {'epoch': self.epoch, 'publish_id': identifier,
            'frame_id': metadata['frame_id'], 'virtual_time_ns': metadata['virtual_time_ns'],
            'raw_sha256': data[56:88].hex(), 'packing': 'experimental-RGGB-packed12',
            'implementation_level': 'C'}
        self.frames[identifier] = Frame(frame.image.copy(), metadata)
        while len(self.frames) > 16:
            self.frames.popitem(last=False)
        if self.directory is None:
            prop, value = 'scene-packet', base64.b64encode(data).decode('ascii')
        else:
            path = self.directory / f'frame-{identifier:016x}.scene'
            try:
                with path.open('xb') as handle:
                    handle.write(data)
            except OSError:
                if path.is_file() and not path.is_symlink():
                    path.unlink()
                self.frames.pop(identifier, None)
                raise
            self.files[identifier] = (path, hashlib.sha256(data).hexdigest())
            prop, value = 'scene-file', path.as_posix()
        self.uncertain = identifier
        try:
            self.qmp.command('qom-set', {'path': self.path, 'property': prop, 'value': value})
        except OSError as exc:
            # A sent command is never retransmitted. A later read can confirm
            # that its ID became active, using the transport's late-reply handling.
            self.last_error = type(exc).__name__ + ': ' + str(exc)
            return False
        except RuntimeError:
            self._discard_file(identifier)
            self.uncertain = None  # explicit native rejection is atomic
            self.frames.pop(identifier, None)
            raise
        self._discard_file(identifier)
        self.uncertain = None
        self.last_error = None
        return True

    def capture_frame(self, now_ns, revision):
        self.observe()
        if self.consumed is None:
            raise CameraError('scene_not_consumed')
        metadata = deepcopy(self.consumed.metadata)
        if metadata.get('scene_revision') != revision:
            raise CameraError('scene_settings_pending')
        age = now_ns - metadata['virtual_time_ns']
        if age < 0:
            raise CameraError('future_scene_frame')
        if age > self.max_age_ns:
            raise CameraError('scene_stale')
        metadata.update(capture_virtual_time_ns=now_ns, native_frame_age_ns=age)
        return Frame(self.consumed.image.copy(), metadata)

    def state(self):
        return {'implementation_level': 'C', 'last_attempt_id': self.sequence,
                'transport': 'file-mailbox' if self.directory is not None else 'base64',
                'publish_outcome_unknown': self.uncertain is not None,
                'last_consumed': deepcopy(self.consumed.metadata['native_scene_source']) if self.consumed else None,
                'last_consumed_revision': self.consumed.metadata.get('scene_revision') if self.consumed else None,
                'max_frame_age_ns': self.max_age_ns, 'observation_gaps': self.observation_gaps,
                'error': self.last_error, 'control_commands_replayed': 0}
