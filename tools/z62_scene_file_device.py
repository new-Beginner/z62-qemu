"""Bounded binary-file transport over the independently frozen r23a scene device."""
from pathlib import Path
import reference_updates as reference

ROOT = Path(__file__).resolve().parents[1]
VERSION = '2026.11.01-r24'
WORK = ROOT / '.build' / ('z62-scene-file-' + VERSION)
HEADER = ROOT / 'qemu/z62-scene-file/nikon-z62-scene-file.h'
INPUTS = {'nikon-z72-input-config.c': 'dc28f5092611a4cde3797b56b382724162ab71533fba4929855c269d416bcc10'}


def identity():
    return {'schema': 1, 'version': VERSION, 'input_sha256': INPUTS,
            'adapter_sha256': reference.sha(Path(__file__).read_bytes()),
            'header_sha256': reference.sha(HEADER.read_bytes()),
            'implementation_level': 'C', 'transport': 'bounded-ordinary-ASCII-file',
            'reuses_scene_packet_validator': True, 'guest_software_patched': False}


def render(data):
    if reference.sha(data) != INPUTS['nikon-z72-input-config.c']:
        raise ValueError('Scene-file transport requires frozen r23a input config')
    text = reference.replace_once(data.decode('utf-8'), '#include "nikon-z62-scene-source.h"',
        '#include "nikon-z62-scene-source.h"\n#include "nikon-z62-scene-file.h"')
    return reference.replace_once(text, '    scene_qom_init(obj);',
                                  '    scene_qom_init(obj);\n    scene_file_qom_init(obj);')


def apply_source(source):
    source = Path(source).resolve()
    if not source.is_relative_to(WORK.resolve()):
        raise ValueError('Scene-file extension requires its independent workspace')
    arm = source / 'hw/arm'
    target = arm / 'nikon-z72-input-config.c'
    target.write_text(render(target.read_bytes()), encoding='utf-8', newline='\n')
    (arm / HEADER.name).write_bytes(HEADER.read_bytes())
    return identity()
