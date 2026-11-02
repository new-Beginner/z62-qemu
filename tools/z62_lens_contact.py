"""Explicit absent-lens board contact, independently recovered for C1.70.

MCU descriptor 2000E33C uses port 40021800 mask1 (PG0). 080308C0
inverts the pad level, then the original debounce/report path sends presence.
This fixture drives only the external pad; it is not a lens protocol peer.
"""
import hashlib
from pathlib import Path
from reference_updates import replace_once

ROOT = Path(__file__).resolve().parents[1]
VERSION = '2026.10.29-lens-contact-r16'


def apply_console(source):
    source = Path(source).resolve()
    if source.is_relative_to(ROOT / 'third_party') or source.is_relative_to(ROOT / '.build'):
        raise ValueError('Absent-lens input applies only to a private runtime console copy')
    path = source / 'tools/z62_console.py'
    text = replace_once(path.read_text(encoding='utf-8'),
                        '        for pin in (1, 13):',
                        '        # C1.70 lens detect PG0: high means physically absent.\n'
                        '        for pin in (0, 1, 13):')
    path.write_text(text, encoding='utf-8', newline='\n')


def identity():
    return {'version': VERSION, 'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'gpio': '/machine/controller/keys-gpio', 'pin': 0, 'level': 1,
            'configuration': 'no lens attached', 'lens_protocol_emulated': False,
            'guest_software_patched': False}
