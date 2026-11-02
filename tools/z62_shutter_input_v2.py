"""Explicitly release both body shutter stages before original controller startup.

The v1 adapter and its mixed half/full observation remain preserved. PG13 has
to be released independently: the MCU suppresses full-press while half is off.
"""
import hashlib
from pathlib import Path
import z62_shutter_input as first

HALF_PRESS = first.HALF_PRESS


def apply_console(source):
    from reference_updates import replace_once
    first.apply_console(source)
    path = source / 'tools/z62_console.py'
    content = replace_once(path.read_text(encoding='utf-8'),
        'from tools.z62_shutter_input import ShutterInputMixin',
        'from tools.z62_shutter_input import ShutterInputMixin\n'
        'from tools.z62_probe import qtest as shutter_qtest')
    content = replace_once(content,
        '        initialize_inputs(self.remote, self.wire, frame_sync=True)',
        '        initialize_inputs(self.remote, self.wire, frame_sync=True)\n'
        '        # Explicit released levels, before the original controller runs.\n'
        '        for pin in (1, 13):\n'
        '            shutter_qtest(self.wire, f"set_irq_in /machine/controller/keys-gpio unnamed-gpio-in {pin} 1")')
    path.write_text(content, encoding='utf-8', newline='\n')


def identity():
    return {**first.identity(), 'version': '2026.10.29-input-r10b',
            'base_source_sha256': first.identity()['source_sha256'],
            'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'released_body_gpio_pins': [1, 13]}
