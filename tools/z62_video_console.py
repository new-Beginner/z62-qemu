"""Opt-in r26 console factory, shared record input and MP4 MIME handling."""
import hashlib
from pathlib import Path

try:
    from .z62_media_scene import MediaSceneMixin
    from .z62_video_scene import VideoSceneCamera, VERSION
    from .z62_video_input import VideoBodyInputMixin
    from .z62_video_card import VideoCard
    from .z62_software_camera import Scene, CameraError, fields
    from .z62_scene_exchange import SceneExchange
except ImportError:
    from z62_media_scene import MediaSceneMixin
    from z62_video_scene import VideoSceneCamera, VERSION
    from z62_video_input import VideoBodyInputMixin
    from z62_video_card import VideoCard
    from z62_software_camera import Scene, CameraError, fields
    from z62_scene_exchange import SceneExchange


class VideoSceneMixin(VideoBodyInputMixin, MediaSceneMixin):
    def _software_locked(self):
        self._ready()
        ticks, frequency = self._key_clock()
        if type(ticks) is not int or ticks < 0 or type(frequency) is not int or frequency <= 0:
            raise CameraError('guest_clock_unavailable')
        now_ns = ticks * 1_000_000_000 // frequency
        epoch = hashlib.sha256(str(self.work).encode('utf-8')).hexdigest()[:24]
        if self._software is None or epoch != self._software_epoch:
            if isinstance(self._software, VideoSceneCamera):
                self._software.abort_video()
            config = self.software_config
            if self._software_card is None and config['card'] is not None:
                root = Path(config['card'])
                self._software_card = VideoCard(root) if root.exists() else VideoCard.create(root)
            scene = Scene.from_image(config['scene']) if config.get('scene') else Scene()
            camera = VideoSceneCamera(card=self._software_card, scene=scene, width=config['width'],
                height=config['height'], clock_epoch=epoch, capture_format=self.media_config['photo_format'],
                video_directory=self.work)
            camera.event('power', {'on': True}, now_ns)
            self._software, self._software_epoch = camera, epoch
            self._scene_revision = 0
            self._scene_published_revision = self._scene_published_frame = None
            self._scene_exchange = SceneExchange(self.qmp, epoch=int(epoch[:16], 16), directory=self.work / 'scene-mailbox')
            camera.native_frame_provider = lambda ns: self._scene_exchange.capture_frame(ns, self._scene_revision)
        camera = self._software
        self._scene_exchange.observe()
        self._scene_publish_locked(camera, now_ns)
        camera.observe_video(now_ns)
        return camera, now_ns

    def software_event(self, request):
        if isinstance(request, dict) and request.get('type') == 'record':
            if set(request) != {'type', 'payload'}:
                raise CameraError('invalid_event_fields')
            fields(request['payload'], ('action',))
            action = request['payload'].get('action')
            if action not in ('start', 'stop', 'cancel'):
                raise CameraError('invalid_record_action')
            with self.io:
                camera, now_ns = self._software_locked()
                if self._video_pending_action is not None or self.key_events.get(29):
                    raise CameraError('record_input_pending')
                if action == 'cancel':
                    return camera.event('record', {'action': action}, now_ns)
                if (action == 'start') == (camera._recorder is not None):
                    raise CameraError('already_recording' if action == 'start' else 'not_recording')
                self._video_pending_action = action
                self._queue_click_locked(29)
                return {'state': camera.status(camera.time_ns), 'result': {'queued': True}}
        return super().software_event(request)

    def close(self):
        with self.io:
            if isinstance(self._software, VideoSceneCamera):
                self._software.abort_video()
        return super().close()


def apply_console(source):
    from reference_updates import replace_once
    source = Path(source)
    target = source / 'tools/z62_console.py'
    content = replace_once(target.read_text(encoding='utf-8'),
        'class Z62Machine(MediaSceneMixin, ModeInputMixin, shared.Machine):',
        'from tools.z62_video_console import VideoSceneMixin\n\n\n'
        'class Z62Machine(VideoSceneMixin, ModeInputMixin, shared.Machine):')
    content = replace_once(content,
        "self.send(200, machine.software_file(self.path[len('/software/file/'):]), 'image/jpeg')",
        "self.send(200, machine.software_file(self.path[len('/software/file/'):]), "
        "'video/mp4' if self.path.endswith('.MP4') else 'application/octet-stream' "
        "if self.path.endswith('.NEF') else 'image/jpeg')")
    target.write_text(content, encoding='utf-8', newline='\n')
    for name in ('z62_video_console.py', 'z62_video_scene.py', 'z62_video_input.py',
                 'z62_video_codec.py', 'z62_video_card.py'):
        (source / 'tools' / name).write_bytes(Path(__file__).with_name(name).read_bytes())
    assets = Path(__file__).with_name('assets')
    html = source / 'web-z62/index.html'
    content = replace_once(html.read_text(encoding='utf-8'), '<form id="software-optics">',
                           (assets / 'z62-video.html').read_text(encoding='utf-8') + '\n<form id="software-optics">')
    html.write_text(content, encoding='utf-8', newline='\n')
    script = source / 'web-z62/console.js'
    content = replace_once(script.read_text(encoding='utf-8'), '      renderMediaControls(state);',
                           '      renderMediaControls(state);\n      renderVideoControls(state, busy);')
    content = replace_once(content,
        "finally { busy = false; document.querySelectorAll('.software-controls button').forEach(button => button.disabled = false); }",
        "finally { busy = false; document.querySelectorAll('.software-controls button').forEach(button => button.disabled = false); "
        "if (videoLastState) renderVideoControls(videoLastState, false); }")
    content = replace_once(content, '  refresh();\n})();', '''  document.getElementById('video-mode').onchange = e => perform(() => event('mode', {mode:e.target.value}));
  for (const action of ['start','stop','cancel'])
    document.getElementById('video-'+action).onclick = () => perform(() => event('record', {action}));
  refresh();
})();''')
    content += '\n' + (assets / 'z62-video.js').read_text(encoding='utf-8')
    script.write_text(content, encoding='utf-8', newline='\n')
