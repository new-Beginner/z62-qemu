"""Opt-in software photo pane; original QEMU firmware inputs remain separate."""
import hashlib
from io import BytesIO
from pathlib import Path

try:
    from .z62_directory_card import DirectoryCard
    from .z62_software_camera import Scene, SoftwareCamera, VERSION
except ImportError:
    from z62_directory_card import DirectoryCard
    from z62_software_camera import Scene, SoftwareCamera, VERSION


class SoftwareCameraMixin:
    def __init__(self, *args, **kwargs):
        self._software_card = self._software = None
        self._software_epoch = None
        super().__init__(*args, **kwargs)

    def _software_locked(self):
        self._ready()
        ticks, frequency = self._key_clock()
        if type(ticks) is not int or ticks < 0 or type(frequency) is not int or frequency <= 0:
            raise ValueError('Guest virtual clock is unavailable')
        now_ns = ticks * 1_000_000_000 // frequency
        epoch = hashlib.sha256(str(self.work).encode('utf-8')).hexdigest()[:24]
        if self._software is None or epoch != self._software_epoch:
            config = self.software_config
            if self._software_card is None and config['card'] is not None:
                root = Path(config['card'])
                self._software_card = (DirectoryCard(root) if root.exists() else DirectoryCard.create(root))
            scene = Scene.from_image(config['scene']) if config.get('scene') else Scene()
            self._software = SoftwareCamera(card=self._software_card, scene=scene,
                width=config['width'], height=config['height'], clock_epoch=epoch)
            self._software_epoch = epoch
        return self._software, now_ns

    def software_status(self):
        with self.io:
            camera, now_ns = self._software_locked()
            return camera.status(now_ns)

    def software_event(self, request):
        if (not isinstance(request, dict) or set(request) != {'type', 'payload'}
                or not isinstance(request['type'], str) or not isinstance(request['payload'], dict)):
            raise ValueError('Expected an explicit software event type and payload')
        with self.io:
            camera, now_ns = self._software_locked()
            return camera.event(request['type'], request['payload'], now_ns)

    def software_frame(self):
        with self.io:
            camera, now_ns = self._software_locked()
            frame = camera.display(now_ns)
            output = BytesIO()
            frame.image.save(output, format='JPEG', quality=86, subsampling=0)
            return output.getvalue()

    def software_file(self, name):
        with self.io:
            camera, _ = self._software_locked()
            if not camera.card:
                raise ValueError('no_card')
            return camera.card.read(name)

    def status(self):
        result = super().status()
        result['software_camera_profile'] = {'version': VERSION, 'implementation_level': 'C',
                                            'factory_capture_chain': False}
        return result

    def close(self):
        try:
            super().close()
        finally:
            if self._software_card is not None:
                self._software_card.close()


def apply_console(source, config):
    """Called only by the separately named C-profile launcher, after mode inputs."""
    from reference_updates import replace_once
    source = Path(source)
    target = source / 'tools/z62_console.py'
    content = replace_once(target.read_text(encoding='utf-8'),
        'class Z62Machine(ModeInputMixin, shared.Machine):',
        'from tools.z62_software_console import SoftwareCameraMixin\n\n\n'
        'class Z62Machine(SoftwareCameraMixin, ModeInputMixin, shared.Machine):\n'
        '    software_config = ' + repr(config))
    content = replace_once(content, "                elif self.path == '/frame':",
        "                elif self.path == '/software/status':\n"
        "                    self.send(200, json.dumps(machine.software_status(), ensure_ascii=False).encode())\n"
        "                elif self.path == '/software/frame':\n"
        "                    self.send(200, machine.software_frame(), 'image/jpeg')\n"
        "                elif self.path.startswith('/software/file/'):\n"
        "                    self.send(200, machine.software_file(self.path[len('/software/file/'):]), 'image/jpeg')\n"
        "                elif self.path == '/frame':")
    content = replace_once(content, "                if self.path == '/key':",
        "                if self.path == '/software/event':\n"
        "                    self.send(200, json.dumps(machine.software_event(request), ensure_ascii=False).encode())\n"
        "                    return\n"
        "                if self.path == '/key':")
    target.write_text(content, encoding='utf-8', newline='\n')
    for name in ('z62_directory_card.py', 'z62_software_camera.py', 'z62_software_console.py'):
        (source / 'tools' / name).write_bytes(Path(__file__).with_name(name).read_bytes())
    assets = Path(__file__).with_name('assets')
    html = source / 'web-z62/index.html'
    html.write_text(replace_once(html.read_text(encoding='utf-8'), '  <div id="notice"',
        (assets / 'z62-software-camera.html').read_text(encoding='utf-8') + '\n  <div id="notice"'),
        encoding='utf-8', newline='\n')
    for target_name, asset_name in (('console.js', 'z62-software-camera.js'), ('style.css', 'z62-software-camera.css')):
        path = source / 'web-z62' / target_name
        path.write_text(path.read_text(encoding='utf-8') + '\n' + (assets / asset_name).read_text(encoding='utf-8'),
                        encoding='utf-8', newline='\n')
