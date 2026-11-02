"""C video lifecycle over the frozen r24 consumed-source and r25 photo models."""
from copy import deepcopy
from io import BytesIO

from PIL import Image

try:
    from .z62_media_scene import MediaSceneCamera
    from .z62_software_camera import Frame, CameraError, fields
    from .z62_video_codec import VideoRecorder, backend
except ImportError:
    from z62_media_scene import MediaSceneCamera
    from z62_software_camera import Frame, CameraError, fields
    from z62_video_codec import VideoRecorder, backend

VERSION = '2026.11.01-video-console-r26b'


class VideoSceneCamera(MediaSceneCamera):
    def __init__(self, *, video_directory, **kwargs):
        self.video_directory = video_directory
        self._recorder = None
        self._video_phase = 'idle'
        self._video_error = None
        self._video_seen = None
        self._video_stats = {'frames': 0, 'buffer_bytes': 0}
        self._last_video = None
        self._video_gaps = 0
        try:
            backend()
            self.video_available = True
        except (ImportError, ValueError, RuntimeError):
            self.video_available = False
        super().__init__(**kwargs)

    def status(self, now_ns):
        state = super().status(now_ns)
        state['video_profile'] = VERSION
        state['capabilities'].update(video=self.video_available, video_implementation_level='C', audio=False,
                                     factory_video=False, photo_video_lever=False)
        state['video'] = dict(self._recorder.status() if self._recorder else self._video_stats,
            phase=self._video_phase, recording=self._recorder is not None, audio=False,
            last_saved=self._last_video, error=deepcopy(self._video_error), observation_gaps=self._video_gaps,
            max_duration_ns=60_000_000_000, max_frames=1800)
        if self.playback and self.card:
            state['selected_media_kind'] = self.card.item(self.playback)['kind']
        return state

    def abort_video(self):
        if self._recorder is not None:
            self._video_stats = self._recorder.status()
            self._recorder.abort()
            self._recorder = None
            self._video_phase = 'cancelled'

    def _video_fail(self, exc):
        self.abort_video()
        self._video_phase = 'error'
        self._video_error = {'type': type(exc).__name__, 'message': str(exc)}

    def observe_video(self, now_ns):
        self._advance(now_ns)
        if self._recorder is None:
            return
        try:
            if now_ns - self._recorder.start_ns > self._recorder.max_duration:
                raise CameraError('video_duration_limit')
            frame = self._consumed_frame(now_ns)
            tag = frame.metadata['native_scene_source']
            if frame.metadata['virtual_time_ns'] > now_ns:
                raise CameraError('video_future_source')
            key = (tag['epoch'], tag['publish_id'])
            # The exchange owns immutable publications. Re-observing one
            # cannot add another encoded frame or invent intermediate images.
            if key == self._video_seen:
                return
            self._recorder.append(frame)
            self._video_seen = key
        except CameraError as exc:
            if str(exc) in ('scene_not_consumed', 'scene_settings_pending', 'scene_stale'):
                self._video_gaps += 1
            else:
                self._video_fail(exc)
        except (OSError, ValueError, RuntimeError, KeyError) as exc:
            self._video_fail(exc)

    def event(self, kind, payload, now_ns):
        if kind != 'record':
            if self._recorder is not None and (kind in ('mode', 'playback', 'delete', 'zoom') or
                                                kind == 'power' and payload.get('on') is False):
                raise CameraError('recording_active: stop or cancel before this operation')
            if kind == 'zoom' and self.playback and self.card.item(self.playback)['kind'] == 'video':
                raise CameraError('video_zoom_unsupported')
            return super().event(kind, payload, now_ns)
        self._advance(now_ns)
        self._on()
        fields(payload, ('action',))
        action = payload.get('action')
        if action == 'start':
            if self._recorder is not None:
                raise CameraError('already_recording')
            if self.mode != 'video':
                raise CameraError('video_mode_required')
            if self.card is None:
                raise CameraError('no_card')
            if self.playback:
                raise CameraError('playback_open')
            if self.card.summary()['free_payload_bytes'] == 0:
                raise CameraError('card_full')
            self._recorder = VideoRecorder(self.video_directory, start_ns=now_ns, clock_epoch=self.clock_epoch)
            self._video_phase, self._video_error, self._video_seen = 'recording', None, None
            self._video_stats = self._recorder.status()
            self._video_gaps = 0
            result = {'recording': True}
        elif action in ('stop', 'cancel'):
            if self._recorder is None:
                raise CameraError('not_recording')
            if action == 'cancel':
                self.abort_video()
                result = {'cancelled': True}
            else:
                self.observe_video(now_ns)
                if self._recorder is None:
                    raise CameraError('video_source_failed: ' + self._video_error['message'])
                recorder = self._recorder
                self._video_stats = recorder.status()
                self._video_phase = 'encoding'
                try:
                    media = recorder.finish(now_ns)
                    self._video_stats = recorder.status()
                    saved = self.card.store_video(**media)
                    self._last_video = saved['name']
                    self._video_phase = 'saved'
                    result = {key: saved[key] for key in ('name', 'bytes', 'sha256', 'kind')}
                except Exception as exc:
                    self._video_fail(exc)
                    raise
                finally:
                    recorder.abort()
                    self._recorder = None
        else:
            raise CameraError('invalid_record_action')
        return {'state': self.status(now_ns), 'result': result}

    def display(self, now_ns):
        if self.playback and self.card.item(self.playback)['kind'] == 'video':
            self._advance(now_ns)
            self._on()
            item = self.card.item(self.playback)
            with Image.open(BytesIO(self.card.read(item['poster']))) as image:
                image.load()
                image = image.convert('RGB')
            return Frame(image, dict(item['metadata'], display_virtual_time_ns=now_ns, video_poster=True))
        return super().display(now_ns)
