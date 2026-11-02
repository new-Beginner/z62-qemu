"""Z62 external body half-press input; no firmware address or software event writes.

UI input 24 is a host identifier, not an expander pin. The original controller
descriptor 9 selects PG1, active low, and its own decoder produces switch bit31.
Raw expander input 0 stays available to research callers with its original meaning.
"""
import hashlib
from pathlib import Path

HALF_PRESS = 24
GPIO_G = '/machine/controller/keys-gpio'


class ShutterInputMixin:
    def _drive_key_pin(self, pin, level):
        if pin == HALF_PRESS:
            self._qtest(f'set_irq_in {GPIO_G} unnamed-gpio-in 1 {level}')
        else:
            self._qtest(f'set_irq_in /machine/peripheral/keys pins {pin} {level}')

    def set_key(self, pin, level):
        if (type(pin) is not int or not 0 <= pin <= HALF_PRESS or
                type(level) is not int or level not in (0, 1)):
            raise ValueError('Invalid key input')
        with self.io:
            self._ready()
            self._set_key_locked(pin, level)

    def _release(self):
        # The inherited release loops over physical expander pins. Release the
        # separate GPIO first, so focus loss/watchdog/close cannot leave it held.
        if HALF_PRESS in self.held:
            self._drive_key_pin(HALF_PRESS, 1)
            self.held.remove(HALF_PRESS)
        super()._release()


def apply_console(source):
    """Deploy this input adapter to the launcher's isolated source copy only."""
    from reference_updates import replace_once
    path = source / 'tools/z62_console.py'
    content = replace_once(path.read_text(encoding='utf-8'),
        'class Z62Machine(shared.Machine):',
        'from tools.z62_shutter_input import ShutterInputMixin\n\n\n'
        'class Z62Machine(ShutterInputMixin, shared.Machine):')
    content = replace_once(content,
        "            self._qtest(f'set_irq_in /machine/peripheral/keys pins {pin} {level}')",
        '            self._drive_key_pin(pin, level)')
    path.write_text(content, encoding='utf-8', newline='\n')
    (source / 'tools/z62_shutter_input.py').write_bytes(Path(__file__).read_bytes())
    html = source / 'web-z62/index.html'
    content = replace_once(html.read_text(encoding='utf-8'),
        '<button class="key" data-pin="0" disabled>EXIT <span class="key-detail">退出 · X</span></button>',
        '<button class="key" data-pin="24" disabled>半按快门 <span class="key-detail">返回拍摄 · X</span></button>')
    html.write_text(content, encoding='utf-8', newline='\n')
    script = source / 'web-z62/console.js'
    content = replace_once(script.read_text(encoding='utf-8'), 'KeyX: 0,', 'KeyX: 24,')
    script.write_text(content, encoding='utf-8', newline='\n')


def identity():
    return {'version': '2026.10.29-input-r10',
            'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'half_press_ui_id': HALF_PRESS, 'gpio_path': GPIO_G, 'gpio_pin': 1,
            'active_level': 0, 'firmware_switch_mask': '0x80000000'}
