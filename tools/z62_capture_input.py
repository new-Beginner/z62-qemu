"""Two-stage physical shutter input for the independently verified r13 device."""
import hashlib
from pathlib import Path
try:
    from .z62_shutter_input import ShutterInputMixin, GPIO_G
except ImportError:
    from z62_shutter_input import ShutterInputMixin, GPIO_G

HALF_PRESS, FULL_PRESS = 24, 25


class CaptureInputMixin(ShutterInputMixin):
    def _capture_input_status(self):
        try:
            target = self._capture_input_target()
            values = {name: self.qmp.command('qom-get', {'path': target, 'property': name}) for name in
                      ('capture-contact-levels', 'capture-contact-edges', 'capture-contact-irq-events')}
            if any(type(v) is not int or v < 0 for v in values.values()):
                raise ValueError('Malformed capture contact counters')
            return {'known': True, **values,
                    'body_input_levels': list(getattr(self, '_body_contact_levels', (1, 1)))}
        except (OSError, RuntimeError, ValueError) as exc:
            return {'known': False, 'error': type(exc).__name__ + ': ' + str(exc)}

    def _capture_input_target(self):
        cached = getattr(self, '_capture_master_path', None)
        if cached:
            return cached
        entries = self.qmp.command('qom-list', {'path': '/machine/unattached'})
        paths = ['/machine/unattached/' + e['name'] for e in entries
                 if e['type'] == 'child<nikon-z72-boot-config>']
        masters = [p for p in paths if self.qmp.command('qom-get', {'path': p, 'property': 'master-role'})]
        if len(masters) != 1:
            raise ValueError('Cannot uniquely identify the capture input hardware')
        target = masters[0]
        if self.qmp.command('qom-get', {'path': target, 'property': 'z62-capture-contacts'}) is not True:
            raise ValueError('Capture contact hardware is not enabled')
        self._capture_master_path = target
        return target

    def _drive_key_pin(self, pin, level):
        if pin not in (HALF_PRESS, FULL_PRESS):
            return super()._drive_key_pin(pin, level)
        target = self._capture_input_target()
        stages = getattr(self, '_body_stages', {HALF_PRESS: 1, FULL_PRESS: 1})
        stages[pin] = level
        self._body_stages = stages
        desired = (int(stages[HALF_PRESS] == 1 and stages[FULL_PRESS] == 1), stages[FULL_PRESS])
        previous = getattr(self, '_body_contact_levels', (1, 1))
        # Full press closes half first. Release opens full before half.
        order = (1, 0) if desired[1] == 1 and previous[1] == 0 else (0, 1)
        for index in order:
            if desired[index] == previous[index]:
                continue
            gpio_pin = (1, 13)[index]
            value = desired[index]
            self._qtest(f'set_irq_in {GPIO_G} unnamed-gpio-in {gpio_pin} {value}')
            self._qtest(f'set_irq_in {target} capture-contact {index} {1-value}')
        self._body_contact_levels = desired

    def set_key(self, pin, level):
        if (type(pin) is not int or not 0 <= pin <= FULL_PRESS or
                type(level) is not int or level not in (0, 1)):
            raise ValueError('Invalid key input')
        with self.io:
            self._ready()
            self._set_key_locked(pin, level)

    def _release(self):
        stages = getattr(self, '_body_stages', {})
        for pin in (FULL_PRESS, HALF_PRESS):
            if pin in self.held or stages.get(pin) == 0:
                self._drive_key_pin(pin, 1)
                self.held.discard(pin)
        super()._release()


def identity():
    return {'version': '2026.10.29-capture-input-r16',
            'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'half_press_ui_id': HALF_PRESS, 'full_press_ui_id': FULL_PRESS,
            'full_press_includes_half': True, 'guest_software_patched': False}


def apply_console(source):
    """Apply after the preserved r10b input adapter to a private source copy."""
    from reference_updates import replace_once
    path = source / 'tools/z62_console.py'
    content = replace_once(path.read_text(encoding='utf-8'),
        'from tools.z62_shutter_input import ShutterInputMixin',
        'from tools.z62_capture_input import CaptureInputMixin')
    content = replace_once(content, 'class Z62Machine(ShutterInputMixin, shared.Machine):',
        'class Z62Machine(CaptureInputMixin, shared.Machine):')
    content = replace_once(content, '        initialize_inputs(self.remote, self.wire, frame_sync=True)',
        '        self._capture_master_path = None\n'
        '        self._body_stages = {24: 1, 25: 1}\n'
        '        self._body_contact_levels = (1, 1)\n'
        '        initialize_inputs(self.remote, self.wire, frame_sync=True)')
    path.write_text(content, encoding='utf-8', newline='\n')
    (source / 'tools/z62_capture_input.py').write_bytes(Path(__file__).read_bytes())
    html = source / 'web-z62/index.html'
    half = '<button class="key" data-pin="24" disabled>半按快门 <span class="key-detail">返回拍摄 · X</span></button>'
    html.write_text(replace_once(html.read_text(encoding='utf-8'), half,
        half + '\n<button class="key" data-pin="25" disabled>全按快门 <span class="key-detail">拍摄 · S</span></button>'),
        encoding='utf-8', newline='\n')
    script = source / 'web-z62/console.js'
    script.write_text(replace_once(script.read_text(encoding='utf-8'), 'KeyX: 24,', 'KeyX: 24, KeyS: 25,'),
                      encoding='utf-8', newline='\n')
