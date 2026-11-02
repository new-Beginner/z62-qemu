"""r27 integration: nonblocking video jobs, compact polling and explicit details."""
import hashlib
from pathlib import Path

try:
    from .z62_video_console import VideoSceneMixin
    from .z62_async_video_scene import AsyncVideoSceneCamera, VERSION
    from .z62_async_video_card import AsyncVideoCard
    from .z62_software_camera import Scene, CameraError, fields
    from .z62_directory_card import plain_path
    from .z62_scene_exchange import SceneExchange
except ImportError:
    from z62_video_console import VideoSceneMixin
    from z62_async_video_scene import AsyncVideoSceneCamera, VERSION
    from z62_async_video_card import AsyncVideoCard
    from z62_software_camera import Scene, CameraError, fields
    from z62_directory_card import plain_path
    from z62_scene_exchange import SceneExchange


class AsyncVideoSceneMixin(VideoSceneMixin):
    def _software_locked(self):
        self._ready()
        ticks, frequency = self._key_clock()
        if type(ticks) is not int or ticks < 0 or type(frequency) is not int or frequency <= 0:
            raise CameraError('guest_clock_unavailable')
        now_ns = ticks * 1_000_000_000 // frequency
        epoch = hashlib.sha256(str(self.work).encode('utf-8')).hexdigest()[:24]
        if self._software is None or epoch != self._software_epoch:
            if isinstance(self._software, AsyncVideoSceneCamera):
                self._software.close_video(timeout=15)
            config = self.software_config
            if self._software_card is None and config['card'] is not None:
                root = Path(config['card'])
                self._software_card = AsyncVideoCard(root) if root.exists() else AsyncVideoCard.create(root)
            jobs = plain_path(self.work.parent / 'video-jobs')
            if not jobs.exists():
                jobs.mkdir()
            plain_path(jobs, directory=True)
            scene = Scene.from_image(config['scene']) if config.get('scene') else Scene()
            camera = AsyncVideoSceneCamera(card=self._software_card, scene=scene, width=config['width'],
                height=config['height'], clock_epoch=epoch, capture_format=self.media_config['photo_format'],
                video_directory=self.work, job_directory=jobs)
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
                if action == 'cancel':
                    return camera.event('record', {'action': action}, now_ns)
                if camera.job_active():
                    raise CameraError('video_job_active')
                if self._video_pending_action is not None or self.key_events.get(29):
                    raise CameraError('record_input_pending')
                if (action == 'start') == (camera._recorder is not None):
                    raise CameraError('already_recording' if action == 'start' else 'not_recording')
                self._video_pending_action = action
                self._queue_click_locked(29)
                return {'state': camera.status(camera.time_ns), 'result': {'queued': True}}
        return super().software_event(request)

    def software_item(self, name):
        with self.io:
            self._ready()
            if self._software_card is None:
                raise CameraError('no_card')
            return self._software_card.full_item(name)

    def software_file(self, name):
        with self.io:
            self._ready()
            if self._software_card is None:
                raise CameraError('no_card')
            return self._software_card.read(name)

    def _cleanup(self):
        # The concrete Z62 cleanup calls super before deleting this VM's work.
        # Confirm the worker is terminal before that source directory disappears.
        if isinstance(self._software, AsyncVideoSceneCamera):
            self._software.close_video(timeout=15)
        return super()._cleanup()

    def close(self):
        with self.io:
            camera = self._software
            if isinstance(camera, AsyncVideoSceneCamera):
                camera.begin_shutdown()
        if isinstance(camera, AsyncVideoSceneCamera):
            camera.close_video(timeout=15)  # join outside the guest/input lock
        return super().close()


def apply_console(source):
    from reference_updates import replace_once
    source = Path(source)
    target = source / 'tools/z62_console.py'
    content = replace_once(target.read_text(encoding='utf-8'),
        'class Z62Machine(VideoSceneMixin, ModeInputMixin, shared.Machine):',
        'from tools.z62_async_video_console import AsyncVideoSceneMixin\n\n\n'
        'class Z62Machine(AsyncVideoSceneMixin, ModeInputMixin, shared.Machine):')
    content = replace_once(content, "                elif self.path.startswith('/software/file/'):",
        "                elif self.path.startswith('/software/item/'):\n"
        "                    self.send(200, json.dumps(machine.software_item(self.path[len('/software/item/'):]), ensure_ascii=False).encode())\n"
        "                elif self.path.startswith('/software/file/'):")
    target.write_text(content, encoding='utf-8', newline='\n')
    for name in ('z62_async_video_console.py', 'z62_async_video_scene.py', 'z62_async_video_card.py',
                 'z62_async_video_job.py', 'z62_async_video_worker.py'):
        (source / 'tools' / name).write_bytes(Path(__file__).with_name(name).read_bytes())
    script = source / 'web-z62/console.js'
    content = replace_once(script.read_text(encoding='utf-8'), '${data.samples.length} 帧',
                           '${data.frame_count ?? data.samples?.length ?? 0} 帧')
    content += '\n' + (Path(__file__).with_name('assets') / 'z62-async-video.js').read_text(encoding='utf-8')
    script.write_text(content, encoding='utf-8', newline='\n')
