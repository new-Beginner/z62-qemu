"""Independent external-scene extension over the frozen r21 device tree."""
from pathlib import Path
import reference_updates as reference

ROOT = Path(__file__).resolve().parents[1]
VERSION = '2026.11.01-r23a'
WORK = ROOT / '.build' / ('z62-scene-source-' + VERSION)
HEADERS = tuple(ROOT / 'qemu/z62-scene-source' / name for name in
                ('nikon-z62-scene-state.h', 'nikon-z62-scene-source.h'))
INPUTS = {
    'nikon-z72-input-config.c': 'd2c0a32577421e6aa3106d124a32137910e3a748955bbf775ca957ffd9c9a058',
    'nikon-z62-functional-raw.h': '8fa7309079741aebf1824810fe1efc01e708c34843b118a8c12976103e58f640',
}


def identity():
    return {'schema': 1, 'version': VERSION, 'input_sha256': INPUTS,
            'adapter_sha256': reference.sha(Path(__file__).read_bytes()),
            'headers_sha256': {p.name: reference.sha(p.read_bytes()) for p in HEADERS},
            'implementation_level': 'C', 'default_enabled': False,
            'frame_geometry': [1514, 1006, 2272], 'packet_header_bytes': 88,
            'completion_after_successful_four_slot_dma_only': True,
            'silicon_packing_calibration_verified': False, 'guest_software_patched': False}


def render(files):
    for name, expected in INPUTS.items():
        if reference.sha(files[name]) != expected:
            raise ValueError('Scene bridge requires the frozen r21 source: ' + name)
    texts = {name: data.decode('utf-8') for name, data in files.items()}
    replace = reference.replace_once
    text = texts['nikon-z72-input-config.c']
    text = replace(text, '#include "nikon-z62-statistics-pixels.h"',
                   '#include "nikon-z62-statistics-pixels.h"\n#include "nikon-z62-scene-state.h"')
    text = replace(text, '    Z62StatisticsPixels continuous_pixels;',
                   '    Z62StatisticsPixels continuous_pixels;\n    Z62SceneSource scene;')
    text = replace(text, '#include "nikon-z62-functional-raw.h"',
                   '#include "nikon-z62-scene-source.h"\n#include "nikon-z62-functional-raw.h"')
    text = replace(text, '    continuous_reset(s);', '    continuous_reset(s);\n    scene_reset(s);')
    text = replace(text, '{ &raw_vmstate, &finite_vmstate, &continuous_vmstate, NULL }',
                   '{ &raw_vmstate, &finite_vmstate, &continuous_vmstate, &scene_vmstate, NULL }')
    text = replace(text, '    object_property_add_str(obj, "raw-last-reason", raw_reason_get, NULL);',
                   '    object_property_add_str(obj, "raw-last-reason", raw_reason_get, NULL);\n    scene_qom_init(obj);')
    text = replace(text, '        DEFINE_PROP_BOOL("functional-raw",',
                   '        DEFINE_PROP_BOOL("scene-source", Z72InputConfig, scene.enabled, false),\n'
                   '        DEFINE_PROP_STRING("scene-initial-file", Z72InputConfig, scene.initial_file),\n'
                   '        DEFINE_PROP_BOOL("functional-raw",')
    texts['nikon-z72-input-config.c'] = text
    raw = texts['nikon-z62-functional-raw.h']
    raw = replace(raw, '       RAW_SUCCESS };', '       RAW_SUCCESS, RAW_SCENE_MISSING };')
    raw = replace(raw, '"address", "overlap", "not-writable-ram", "dma-error", "success"',
                  '"address", "overlap", "not-writable-ram", "dma-error", "success", "scene-missing"')
    first = '    for (unsigned y = 0; y < RAW_HEIGHT; y++) {'
    start = raw.index(first)
    end = raw.index('    for (unsigned i = 0; i < 4; i++) {', start)
    pattern = raw[start:end].rstrip()
    block = '''    if (s->scene.enabled) {
        if (!s->scene.valid) {
            raw_reject(s, RAW_SCENE_MISSING);
            return;
        }
        memcpy(frame, s->scene.pixels, RAW_BYTES);
    } else {
''' + '\n'.join('    ' + line for line in pattern.splitlines()) + '\n    }\n'
    raw = raw[:start] + block + raw[end:]
    raw = replace(raw, '    s->raw_reason = RAW_SUCCESS;',
                  '    s->raw_reason = RAW_SUCCESS;\n    scene_used(s);')
    raw = replace(raw, '    if (s->raw_root) {\n        address_space_init',
                  '    if (!scene_realize(s, errp)) { return; }\n    if (s->raw_root) {\n        address_space_init')
    texts['nikon-z62-functional-raw.h'] = raw
    return texts


def apply_source(source):
    source = Path(source).resolve()
    if not source.is_relative_to(WORK.resolve()):
        raise ValueError('Scene bridge requires its independent r23 workspace')
    arm = source / 'hw/arm'
    for name, text in render({name: (arm / name).read_bytes() for name in INPUTS}).items():
        (arm / name).write_text(text, encoding='utf-8', newline='\n')
    for header in HEADERS:
        (arm / header.name).write_bytes(header.read_bytes())
    return identity()
