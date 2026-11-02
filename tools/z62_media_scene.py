"""r25 C-level JPEG/NEF capture over the frozen r24 native scene interface."""
from copy import deepcopy
import hashlib
from io import BytesIO
import json
from pathlib import Path

from PIL import Image

try:
    from .z62_native_scene_console import NativeSceneCamera, NativeSceneMixin
    from .z62_software_camera import Scene, Frame, CameraError, fields
    from .z62_scene_exchange import SceneExchange
    from .z62_media_card import MediaCard
    from .z62_nef_codec import encode_nef, raw14_from_consumed_frame, inspect_nef
except ImportError:
    from z62_native_scene_console import NativeSceneCamera, NativeSceneMixin
    from z62_software_camera import Scene, Frame, CameraError, fields
    from z62_scene_exchange import SceneExchange
    from z62_media_card import MediaCard
    from z62_nef_codec import encode_nef, raw14_from_consumed_frame, inspect_nef

VERSION = '2026.11.01-media-console-r25'
FORMATS = ('jpeg', 'nef', 'jpeg-nef')


class MediaSceneCamera(NativeSceneCamera):
    def __init__(self, *, capture_format='jpeg-nef', **kwargs):
        if capture_format not in FORMATS:
            raise CameraError('invalid_photo_format')
        self.capture_format = capture_format
        super().__init__(**kwargs)

    def status(self, now_ns):
        state = super().status(now_ns)
        state.update(media_profile=VERSION, capture_format=self.capture_format)
        state['capabilities'].update(nef=True, nef_implementation_level='C',
                                     nef_effective_source_bits=12, nef_storage_bits=14)
        return state

    def _capture(self, now_ns):
        self._on()
        if not self.card:
            raise CameraError('no_card')
        if self.mode != 'photo':
            raise CameraError('wrong_mode')
        frame = self._consumed_frame(now_ns)
        metadata = deepcopy(frame.metadata)
        metadata.update(photo_format=self.capture_format, media_profile=VERSION)
        if self.capture_format == 'jpeg':
            output = BytesIO()
            exif = Image.Exif()
            exif[270] = json.dumps(metadata, sort_keys=True, separators=(',', ':'))
            exif[305] = VERSION + ' explicit JPEG C'
            frame.image.save(output, format='JPEG', quality=92, subsampling=0, exif=exif)
            return self.card.store_photo(jpeg=output.getvalue(), nef=None, metadata=metadata)
        raw, metadata = raw14_from_consumed_frame(Frame(frame.image, metadata))
        nef = encode_nef(raw, frame.image, metadata)
        info = inspect_nef(nef)
        metadata = info['description']
        jpeg = nef[info['preview_offset']:info['preview_offset'] + info['preview_bytes']] if self.capture_format == 'jpeg-nef' else None
        return self.card.store_photo(jpeg=jpeg, nef=nef, metadata=metadata)

    def display(self, now_ns):
        self._advance(now_ns)
        self._on()
        if not self.playback or not self.playback.endswith('.NEF'):
            return super().display(now_ns)
        item = self.card.item(self.playback)
        data = self.card.read(self.playback)
        info = inspect_nef(data)
        with Image.open(BytesIO(data[info['preview_offset']:info['preview_offset'] + info['preview_bytes']])) as image:
            image.load()
            image = image.convert('RGB')
        if self.zoom > 1:
            width, height = image.width / self.zoom, image.height / self.zoom
            left, top = (image.width - width) / 2, (image.height - height) / 2
            image = image.crop((left, top, left + width, top + height)).resize((self.width, self.height), Image.Resampling.NEAREST)
        return Frame(image, dict(item['metadata'], display_virtual_time_ns=now_ns, playback_zoom=self.zoom))


class MediaSceneMixin(NativeSceneMixin):
    def _software_locked(self):
        self._ready()
        ticks, frequency = self._key_clock()
        if type(ticks) is not int or ticks < 0 or type(frequency) is not int or frequency <= 0:
            raise CameraError('guest_clock_unavailable')
        now_ns = ticks * 1_000_000_000 // frequency
        epoch = hashlib.sha256(str(self.work).encode('utf-8')).hexdigest()[:24]
        if self._software is None or epoch != self._software_epoch:
            config = self.software_config
            if self._software_card is None and config['card'] is not None:
                root = Path(config['card'])
                self._software_card = MediaCard(root) if root.exists() else MediaCard.create(root)
            scene = Scene.from_image(config['scene']) if config.get('scene') else Scene()
            camera = MediaSceneCamera(card=self._software_card, scene=scene, width=config['width'],
                                      height=config['height'], clock_epoch=epoch,
                                      capture_format=self.media_config['photo_format'])
            camera.event('power', {'on': True}, now_ns)
            self._software, self._software_epoch = camera, epoch
            self._scene_revision = 0
            self._scene_published_revision = self._scene_published_frame = None
            self._scene_exchange = SceneExchange(self.qmp, epoch=int(epoch[:16], 16), directory=self.work / 'scene-mailbox')
            camera.native_frame_provider = lambda ns: self._scene_exchange.capture_frame(ns, self._scene_revision)
        camera = self._software
        self._scene_exchange.observe()
        self._scene_publish_locked(camera, now_ns)
        return camera, now_ns

    def software_event(self, request):
        if isinstance(request, dict) and request.get('type') == 'photo-format':
            if set(request) != {'type', 'payload'}:
                raise CameraError('invalid_event_fields')
            fields(request['payload'], ('format',))
            value = request['payload'].get('format')
            if value not in FORMATS:
                raise CameraError('invalid_photo_format')
            with self.io:
                camera, now_ns = self._software_locked()
                camera.capture_format = value
                return {'state': camera.status(now_ns), 'result': {'format': value}}
        return super().software_event(request)


def apply_console(source, config):
    from reference_updates import replace_once
    source = Path(source)
    target = source / 'tools/z62_console.py'
    content = replace_once(target.read_text(encoding='utf-8'),
        'class Z62Machine(NativeSceneMixin, ModeInputMixin, shared.Machine):',
        'from tools.z62_media_scene import MediaSceneMixin\n\n\n'
        'class Z62Machine(MediaSceneMixin, ModeInputMixin, shared.Machine):\n'
        '    media_config = ' + repr(config))
    target.write_text(content, encoding='utf-8', newline='\n')
    for name in ('z62_media_scene.py', 'z62_media_card.py', 'z62_nef_codec.py'):
        (source / 'tools' / name).write_bytes(Path(__file__).with_name(name).read_bytes())
    html = source / 'web-z62/index.html'
    content = replace_once(html.read_text(encoding='utf-8'),
        '<button id="software-shutter">拍摄 JPEG</button>', '<button id="software-shutter">拍摄照片</button>')
    content = replace_once(content, '<form id="software-optics">',
        '<label>照片格式 <select id="media-format"><option value="jpeg">JPEG</option>'
        '<option value="nef">NEF</option><option value="jpeg-nef">JPEG＋NEF</option></select></label>\n'
        '        <form id="software-optics">')
    content = replace_once(content, '<a id="software-download" hidden download>下载当前照片</a>',
        '<a id="software-download" hidden download>下载当前照片</a> '
        '<a id="media-download-nef" hidden download>下载NEF · C模型</a>')
    content = replace_once(content, '原厂照片编码、NEF、录像与AF尚未贯通。',
        'NEF为C级F0无损编码（原生12有效位存入14位），原厂照片编码、录像与AF仍未贯通。')
    html.write_text(content, encoding='utf-8', newline='\n')
    script = source / 'web-z62/console.js'
    content = replace_once(script.read_text(encoding='utf-8'), '      renderNativeSoftwareInfo(state);',
                           '      renderNativeSoftwareInfo(state);\n      renderMediaControls(state);')
    content += '''
function renderMediaControls(state) {
  const selector = document.getElementById('media-format');
  if (selector) selector.value = state.capture_format || 'jpeg';
  const item = (state.card.images || []).find(row => row.name === state.selected_image);
  const nef = item?.files?.find(row => row.name.endsWith('.NEF'));
  const link = document.getElementById('media-download-nef');
  link.hidden = !nef;
  if (nef) link.href = '/software/file/' + encodeURIComponent(nef.name);
}
document.getElementById('media-format').addEventListener('change', async event => {
  const response = await fetch('/camera/event', {method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({type:'photo-format',payload:{format:event.target.value}})});
  const result = await response.json();
  document.getElementById('software-message').textContent = response.ok ? '照片格式已设置' : result.error;
});
'''
    script.write_text(content, encoding='utf-8', newline='\n')
