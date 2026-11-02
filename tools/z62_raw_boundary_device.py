"""Independent RAW-ingress boundary extension over frozen r13."""
from pathlib import Path
import reference_updates as reference

ROOT = Path(__file__).resolve().parents[1]
VERSION = '2026.10.29-r17'
WORK = ROOT / '.build' / ('z62-raw-boundary-' + VERSION)
HEADER = ROOT / 'qemu/z62-raw-boundary/nikon-z62-raw-boundary.h'
INPUT_SHA = '2076188b6908768400afdebb46c6a7aedc4ecaefaea4ea6c82942b09aa11449f'


def identity():
    return {'schema': 1, 'version': VERSION, 'input_sha256': INPUT_SHA,
            'adapter_sha256': reference.sha(Path(__file__).read_bytes()),
            'header_sha256': reference.sha(HEADER.read_bytes()), 'default_enabled': False,
            'source': 'successful owned native RAW DMA on original frame clock',
            'status_register': '0x20068210', 'status_bit': 0, 'irq': 94,
            'silicon_timing_verified': False, 'statistics_completion_implemented': False,
            'guest_software_patched': False, 'photo_capture_verified': False}


def render(data):
    if reference.sha(data) != INPUT_SHA:
        raise ValueError('RAW boundary requires exact frozen r13 board source')
    text = data.decode('utf-8')
    replace = reference.replace_once
    text = replace(text, '    bool z62_capture_contacts;',
                   '    bool z62_capture_contacts;\n    bool z62_raw_boundary;\n'
                   '    uint64_t raw_boundary_events, raw_boundary_coalesced;')
    text = replace(text, '#include "nikon-z62-raw-stream.h"',
                   '#include "nikon-z62-raw-stream.h"\n#include "nikon-z62-raw-boundary.h"')
    text = replace(text, '    raw_stream_frame(s, 0, 1);\n    raw_stream_frame(s, 0, 0);',
                   '    raw_boundary_frame(s, 0, 1);\n    raw_boundary_frame(s, 0, 0);')
    text = replace(text, 'qdev_init_gpio_in_named(DEVICE(obj), raw_stream_frame, "raw-stream-frame", 1);',
                   'qdev_init_gpio_in_named(DEVICE(obj), raw_boundary_frame, "raw-stream-frame", 1);')
    text = replace(text, '    raw_stream_reset(s);', '    raw_stream_reset(s);\n    raw_boundary_reset(s);')
    text = replace(text, '    .version_id = 43,\n    .minimum_version_id = 43,',
                   '    .version_id = 44,\n    .minimum_version_id = 44,')
    text = replace(text, '        VMSTATE_UINT32(capture_contact_levels, NikonZ72BootConfig),',
                   '        VMSTATE_UINT64(raw_boundary_events, NikonZ72BootConfig),\n'
                   '        VMSTATE_UINT64(raw_boundary_coalesced, NikonZ72BootConfig),\n'
                   '        VMSTATE_UINT32(capture_contact_levels, NikonZ72BootConfig),')
    text = replace(text, '    object_property_add_bool(obj, "raw-stream-active", raw_stream_active_get, NULL);',
                   '    object_property_add_uint64_ptr(obj, "raw-boundary-events", &s->raw_boundary_events, OBJ_PROP_FLAG_READ);\n'
                   '    object_property_add_uint64_ptr(obj, "raw-boundary-coalesced", &s->raw_boundary_coalesced, OBJ_PROP_FLAG_READ);\n'
                   '    object_property_add_bool(obj, "raw-stream-active", raw_stream_active_get, NULL);')
    text = replace(text, '        DEFINE_PROP_BOOL("z62-capture-contacts",',
                   '        DEFINE_PROP_BOOL("z62-raw-boundary", NikonZ72BootConfig, z62_raw_boundary, false),\n'
                   '        DEFINE_PROP_BOOL("z62-capture-contacts",')
    return text


def apply_source(source):
    source = Path(source).resolve()
    if not source.is_relative_to(WORK.resolve()):
        raise ValueError('RAW boundary requires independent r17 workspace')
    board = source / 'hw/arm/nikon-z72.c'
    board.write_text(render(board.read_bytes()), encoding='utf-8', newline='\n')
    (board.parent / HEADER.name).write_bytes(HEADER.read_bytes())
    return identity()
