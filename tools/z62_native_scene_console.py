"""Native RAW input + shared body edges + explicitly substituted C JPEG."""
from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
import threading
import traceback

from PIL import Image

try:
    from .z62_software_camera import SoftwareCamera, Scene, Frame, CameraError, fields
    from .z62_software_console import SoftwareCameraMixin
    from .z62_unified_camera_input import UnifiedCameraInputMixin
    from .z62_scene_exchange import SceneExchange
    from .z62_scene_packet import make_packet
except ImportError:
    from z62_software_camera import SoftwareCamera, Scene, Frame, CameraError, fields
    from z62_software_console import SoftwareCameraMixin
    from z62_unified_camera_input import UnifiedCameraInputMixin
    from z62_scene_exchange import SceneExchange
    from z62_scene_packet import make_packet

VERSION = '2026.11.01-native-scene-console-r24'


class NativeSceneCamera(SoftwareCamera):
    native_frame_provider = None

    def _consumed_frame(self, now_ns):
        if self.native_frame_provider is None:
            raise CameraError('scene_not_consumed')
        return self.native_frame_provider(now_ns)

    def _capture(self, now_ns):
        self._on()
        if not self.card:
            raise CameraError('no_card')
        if self.mode != 'photo':
            raise CameraError('wrong_mode')
        frame = self._consumed_frame(now_ns)
        exif = Image.Exif()
        exif[270] = json.dumps(frame.metadata, sort_keys=True, separators=(',', ':'))
        exif[305] = 'Z62-QEMU native-input software JPEG C'
        output = BytesIO()
        frame.image.save(output, format='JPEG', quality=92, subsampling=0, exif=exif)
        return self.card.store_jpeg(output.getvalue(), frame.metadata)

    def display(self, now_ns):
        self._advance(now_ns)
        self._on()
        return super().display(now_ns) if self.playback else self._consumed_frame(now_ns)


class NativeSceneMixin(UnifiedCameraInputMixin, SoftwareCameraMixin):
    def __init__(self, *args, **kwargs):
        self._scene_exchange = None
        self._scene_revision = 0
        self._scene_published_revision = None
        self._scene_published_frame = None
        self._scene_thread_error = None
        self._scene_thread = None
        super().__init__(*args, **kwargs)
        if self.software_config.get('auto_scene_pump', True):
            self._scene_thread = threading.Thread(target=self._scene_loop, daemon=True)
            self._scene_thread.start()

    def _software_locked(self):
        camera, now_ns = super()._software_locked()
        if not isinstance(camera, NativeSceneCamera):
            camera = NativeSceneCamera(card=camera.card, width=camera.width, height=camera.height,
                                       scene=camera.scene, clock_epoch=camera.clock_epoch)
            camera.event('power', {'on': True}, now_ns)
            self._software = camera
            self._scene_revision = 0
            self._scene_published_revision = self._scene_published_frame = None
            self._scene_exchange = SceneExchange(self.qmp, epoch=int(camera.clock_epoch[:16], 16),
                                                  directory=self.work / 'scene-mailbox')
            camera.native_frame_provider = lambda ns: self._scene_exchange.capture_frame(ns, self._scene_revision)
        self._scene_exchange.observe()
        self._scene_publish_locked(camera, now_ns)
        return camera, now_ns

    def _scene_publish_locked(self, camera, now_ns, force=False):
        frame_id = now_ns * 30 // 1_000_000_000
        if (not camera.powered or (not force and self._scene_published_revision == self._scene_revision
                                   and self._scene_published_frame == frame_id)):
            return
        frame = camera.frame(now_ns)
        frame.metadata['scene_revision'] = self._scene_revision
        if self._scene_exchange.publish(frame):
            self._scene_published_revision, self._scene_published_frame = self._scene_revision, frame_id

    def _scene_loop(self):
        while not self.shutdown.wait(.05):
            with self.io:
                if self.phase != 'running':
                    continue
                try:
                    self._software_locked()
                    self._scene_thread_error = None
                except (OSError, ValueError, RuntimeError) as exc:
                    self._scene_thread_error = {'type': type(exc).__name__, 'message': str(exc),
                                                'traceback': traceback.format_exc()}

    def native_scene_status(self):
        state = self._scene_exchange.state() if self._scene_exchange else {'last_consumed': None}
        state.update(version=VERSION, scene_revision=self._scene_revision,
                     current_settings_consumed=state.get('last_consumed_revision') == self._scene_revision,
                     source_thread_error=deepcopy(self._scene_thread_error), factory_capture_chain_verified=False)
        return state

    def software_status(self):
        with self.io:
            camera, now_ns = self._software_locked()
            state = camera.status(now_ns)
            state['native_scene'] = self.native_scene_status()
            state['capabilities']['qemu_sensor_scene_bridge'] = state['native_scene'].get('last_consumed') is not None
            return state

    def _queue_click_locked(self, pin):
        self._set_key_locked(pin, 0)
        self._set_key_locked(pin, 1)

    def software_event(self, request):
        if (not isinstance(request, dict) or set(request) != {'type', 'payload'}
                or not isinstance(request['type'], str) or not isinstance(request['payload'], dict)):
            raise ValueError('Expected an explicit camera event type/payload')
        kind, payload = request['type'], request['payload']
        with self.io:
            camera, now_ns = self._software_locked()
            result = {'queued': True}
            if kind == 'shutter':
                fields(payload, ('stage', 'pressed'))
                if payload.get('stage') not in ('half', 'full') or type(payload.get('pressed')) is not bool:
                    raise CameraError('invalid_shutter')
                self._set_key_locked(24 if payload['stage'] == 'half' else 25, int(not payload['pressed']))
            elif kind == 'playback':
                fields(payload, ('action',))
                action = payload.get('action')
                if action not in ('open', 'close', 'next', 'previous'):
                    raise CameraError('invalid_playback')
                self._queue_click_locked({'open': 8, 'close': 24, 'next': 6, 'previous': 7}[action])
            elif kind == 'delete':
                fields(payload, ())
                self._queue_click_locked(23)
            elif kind == 'zoom':
                fields(payload, ('factor',))
                target = payload.get('factor')
                if type(target) is not int or target not in (1, 2, 4, 8, 16):
                    raise CameraError('invalid_zoom')
                if not camera.playback:
                    raise CameraError('playback_required')
                if any(self.key_events.get(pin) for pin in (21, 22)):
                    raise CameraError('zoom_busy')
                value = camera.zoom
                while value != target:
                    pin = 22 if target > value else 21
                    self._queue_click_locked(pin)
                    value = value * 2 if pin == 22 else value // 2
            else:
                result = camera.event(kind, payload, now_ns)['result']
                if kind in ('power', 'lens', 'exposure', 'mode'):
                    self._scene_revision += 1
                    self._scene_publish_locked(camera, now_ns, force=True)
            # Immediate queue delivery can observe a later guest tick in the
            # body-edge callback. Respond at that already-observed model time.
            state = camera.status(camera.time_ns)
            state['native_scene'] = self.native_scene_status()
            return {'state': state, 'result': result}

    def camera_event(self, request):
        if not isinstance(request, dict) or set(request) != {'type', 'payload'} or not isinstance(request['payload'], dict):
            raise ValueError('Expected camera event type/payload')
        kind, payload = request['type'], request['payload']
        methods = {'key': lambda: self.set_key(payload.get('pin'), payload.get('level')),
                   'rotate': lambda: self.rotate(payload.get('encoder'), payload.get('steps')),
                   'joystick': lambda: self.set_joystick(payload.get('position')),
                   'body-mode': lambda: self.set_mode(payload.get('position')),
                   'mode-lock': lambda: self.set_mode_lock(payload.get('pressed')),
                   'release': self.release, 'heartbeat': self.heartbeat}
        if kind in methods:
            methods[kind]()
            return {'ok': True, 'result': {'queued': True}}
        return self.software_event(request)

    def camera_status(self):
        return {'firmware': self.status(), 'software_camera': self.software_status(),
                'input': self.camera_input_status(), 'atomic_cross_device_snapshot': False}

    def close(self):
        try:
            super().close()
        finally:
            if self._scene_thread is not None:
                self._scene_thread.join(timeout=10)
                if self._scene_thread.is_alive():
                    raise RuntimeError('Scene source thread did not close')


def apply_console(source, config):
    from reference_updates import replace_once
    source = Path(source)
    scene = Scene.from_image(config['scene']) if config.get('scene') else Scene()
    initial = SoftwareCamera(width=config['width'], height=config['height'], scene=scene)
    initial.event('power', {'on': True}, 0)
    packet = make_packet(initial.frame(0).image, epoch=0, publish_id=1, frame_id=0, virtual_time_ns=0)
    initial_path = source / 'native-initial.scene'
    with initial_path.open('xb') as handle:
        handle.write(packet)
    target = source / 'tools/z62_console.py'
    content = replace_once(target.read_text(encoding='utf-8'),
        'class Z62Machine(SoftwareCameraMixin, ModeInputMixin, shared.Machine):',
        'from tools.z62_native_scene_console import NativeSceneMixin\n\n\n'
        'class Z62Machine(NativeSceneMixin, ModeInputMixin, shared.Machine):')
    content = replace_once(content, '        for device in devices:',
        '        command += ' + repr(['-global', 'nikon-z72-input-config.scene-source=on',
                                     '-global', 'nikon-z72-input-config.scene-initial-file=' + str(initial_path)]) +
        '\n        for device in devices:')
    content = replace_once(content, "                elif self.path == '/software/status':",
        "                elif self.path == '/camera/status':\n"
        "                    self.send(200, json.dumps(machine.camera_status(), ensure_ascii=False).encode())\n"
        "                elif self.path == '/software/status':")
    content = replace_once(content, "                if self.path == '/software/event':",
        "                if self.path == '/camera/event':\n"
        "                    self.send(200, json.dumps(machine.camera_event(request), ensure_ascii=False).encode())\n"
        "                    return\n"
        "                if self.path == '/software/event':")
    content = replace_once(content, "        if self.phase != 'running':\n            return state",
        '        state["native_scene"] = self.native_scene_status()\n'
        '        state["shared_camera_input"] = self.camera_input_status()\n'
        "        if self.phase != 'running':\n            return state")
    target.write_text(content, encoding='utf-8', newline='\n')
    for name in ('z62_native_scene_console.py', 'z62_unified_camera_input.py', 'z62_scene_exchange.py', 'z62_scene_packet.py'):
        (source / 'tools' / name).write_bytes(Path(__file__).with_name(name).read_bytes())
    script = source / 'web-z62/console.js'
    content = replace_once(script.read_text(encoding='utf-8'), 'async function request(path, body = {}) {',
        "async function request(path, body = {}) {\n"
        "  const routes = {'/key':'key','/rotate':'rotate','/joystick':'joystick','/mode':'body-mode','/mode-lock':'mode-lock','/release':'release','/heartbeat':'heartbeat'};\n"
        "  if (routes[path]) { body = {type:routes[path],payload:body}; path='/camera/event'; }")
    content = replace_once(content, "fetch('/software/event',", "fetch('/camera/event',")
    content = replace_once(content,
        "      const saved = await event('shutter', {stage:'full',pressed:true});\n"
        "      el('info').textContent = `已保存 ${saved.result.name}`;",
        "      await event('shutter', {stage:'full',pressed:true});\n"
        "      el('info').textContent = '快门输入已排队；照片以后台保存结果为准';")
    content = replace_once(content, "    running = state.phase === 'running' && state.execution === 'running';",
        "    renderNativeInputReceipt(state);\n"
        "    running = state.phase === 'running' && state.execution === 'running';")
    content = replace_once(content, '    busy = true;',
        '    busy = true;\n    const receiptBeforeAction = nativeReceiptSeq;')
    content = replace_once(content, "    try { await action(); el('message').textContent = '操作已完成'; }",
        "    try { await action(); if (nativeReceiptSeq === receiptBeforeAction) el('message').textContent = '输入已接收，等待后台结果。'; }")
    info_lines = [line for line in content.splitlines() if "el('info').textContent = `${state.view" in line]
    if len(info_lines) != 1:
        raise ValueError('Expected exactly one software frame-information renderer')
    content = replace_once(content, info_lines[0], '      renderNativeSoftwareInfo(state);')
    content += '\n' + (Path(__file__).with_name('assets') / 'z62-native-scene-status.js').read_text(encoding='utf-8')
    script.write_text(content, encoding='utf-8', newline='\n')
    html = source / 'web-z62/index.html'
    content = replace_once(html.read_text(encoding='utf-8'),
        '此窗口使用虚拟镜头和软件 JPEG。上方原厂固件画面保持独立；原厂拍摄、NEF、录像和自动对焦尚未贯通。',
        '场景输入已连接原生RAW设备；机身快门、回放、缩放和删除共用输入事件。JPEG仍为C级软件编码，原厂照片编码、NEF、录像与AF尚未贯通。')
    html.write_text(content, encoding='utf-8', newline='\n')
