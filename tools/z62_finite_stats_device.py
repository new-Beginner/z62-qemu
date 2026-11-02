"""Hash-bound independent r8 finite-statistics device adapter."""
from pathlib import Path
import reference_updates as reference

ROOT = Path(__file__).resolve().parents[1]
VERSION = '2026.10.29-r8'
WORK = ROOT/'.build'/('z62-finite-stats-'+VERSION)
HEADERS = tuple(ROOT/'qemu/z62-finite-stats'/name for name in
                ('nikon-z62-finite-stats.h', 'nikon-z62-finite-bridge.h'))
INPUTS = {
    'nikon-z72.c': '417a062a721476a5f0274aa82a2c9279ae94b5bef4318b3d16bbfd87f623ae55',
    'nikon-z72-input-config.c': '70f5bbf0cf4f0e054b5fe9718be4ad5256845171f973e6d6db8f2a55a33d6b4c',
    'nikon-z62-functional-raw.h': '7df661209e4ad1b8036d5fab4d8965a54ad2df2501651111e9579ae1f3ed578e',
}


def identity():
    return {'schema': 1, 'version': VERSION, 'input_sha256': INPUTS,
        'adapter_sha256': reference.sha(Path(__file__).read_bytes()),
        'headers_sha256': {p.name: reference.sha(p.read_bytes()) for p in HEADERS},
        'default_enabled': False, 'data_layout': '30x12 LE-u16, row64, slots61',
        'algorithm_hypothesis': 'stationary last-RAW full-frame regional box means',
        'silicon_metering_verified': False, 'camera_safety_verified': False,
        'guest_software_patched': False, 'isp_implemented': False}


def render(files):
    for name, expected in INPUTS.items():
        if reference.sha(files[name]) != expected:
            raise ValueError('Finite stats input SHA mismatch: '+name)
    texts = {name: data.decode('utf-8') for name, data in files.items()}
    replace = reference.replace_once
    text = texts['nikon-z72-input-config.c']
    text = replace(text, '    qemu_irq raw_complete;', '''    qemu_irq raw_complete;
    bool functional_finite_stats, finite_enabled, finite_active, finite_done;
    bool finite_clock_level, finite_rearm;
    uint32_t finite_source, finite_destination, finite_pitch, finite_index;
    uint32_t finite_geometry, finite_reason, finite_config[11];
    uint8_t finite_pixels[768];
    uint64_t finite_attempts, finite_frames, finite_batches, finite_rejected, finite_bytes;
    qemu_irq finite_enable_irq, finite_ready_irq, finite_complete_irq;''')
    text = replace(text, '#include "nikon-z62-functional-raw.h"',
                   '#include "nikon-z62-functional-raw.h"\n#include "nikon-z62-finite-stats.h"')
    text = replace(text, '    s->raw_reason = RAW_RESET;',
                   '    s->raw_reason = RAW_RESET;\n    finite_reset(s);')
    text = replace(text, '{ &raw_vmstate, NULL }', '{ &raw_vmstate, &finite_vmstate, NULL }')
    text = replace(text, '    qdev_init_gpio_in_named(DEVICE(s), raw_submit, "raw-submit", 1);', '''    qdev_init_gpio_in_named(DEVICE(s), raw_submit, "raw-submit", 1);
    qdev_init_gpio_in_named(DEVICE(obj), finite_enable, "finite-enable", 1);
    qdev_init_gpio_in_named(DEVICE(obj), finite_commit, "finite-commit", 1);
    qdev_init_gpio_in_named(DEVICE(obj), finite_frame, "finite-frame", 1);
    qdev_init_gpio_out_named(DEVICE(obj), &s->finite_ready_irq, "finite-ready", 1);
    qdev_init_gpio_out_named(DEVICE(obj), &s->finite_complete_irq, "finite-complete", 1);
    object_property_add_uint64_ptr(obj, "finite-attempts", &s->finite_attempts, OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(obj, "finite-frames", &s->finite_frames, OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(obj, "finite-batches", &s->finite_batches, OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(obj, "finite-rejected", &s->finite_rejected, OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(obj, "finite-bytes", &s->finite_bytes, OBJ_PROP_FLAG_READ);
    object_property_add_str(obj, "finite-reason", finite_reason_get, NULL);''')
    text = replace(text, '        DEFINE_PROP_BOOL("functional-raw",',
                   '        DEFINE_PROP_BOOL("functional-finite-stats", Z72InputConfig, functional_finite_stats, false),\n'
                   '        DEFINE_PROP_BOOL("functional-raw",')
    texts['nikon-z72-input-config.c'] = text
    texts['nikon-z62-functional-raw.h'] = replace(texts['nikon-z62-functional-raw.h'],
        '    s->raw_accepted++;', '    s->raw_accepted++;\n    s->finite_source = dst[0]; /* actual successful DMA source */')
    board = texts['nikon-z72.c']
    board = replace(board, '    bool z62_raw_stream,', '''    bool z62_finite_stats, finite_started;
    qemu_irq finite_enable_irq, finite_frame_irq, finite_commit_irq;
    bool z62_raw_stream,''')
    board = replace(board, '#include "nikon-z62-raw-stream.h"',
                    '#include "nikon-z62-raw-stream.h"\n#include "nikon-z62-finite-bridge.h"')
    needle = 'raw_stream_control(s, address, value);'
    if board.count(needle) != 3:
        raise ValueError('Finite bridge control anchors changed')
    board = board.replace(needle, needle+'\n        finite_bridge_control(s, address, value);')
    board = replace(board, '    s->frame_sync_count++;', '    finite_bridge_frame(s);\n    s->frame_sync_count++;')
    board = replace(board, '    raw_stream_reset(s);', '''    raw_stream_reset(s);
    s->finite_started = false;
    qemu_set_irq(s->finite_enable_irq, 0);
    qemu_set_irq(s->finite_frame_irq, 0);
    qemu_set_irq(s->finite_commit_irq, 0);''')
    board = replace(board, '    .version_id = 40,\n    .minimum_version_id = 40,',
                    '    .version_id = 41,\n    .minimum_version_id = 41,')
    board = replace(board, '        VMSTATE_BOOL(raw_stream_started, NikonZ72BootConfig),',
                    '        VMSTATE_BOOL(finite_started, NikonZ72BootConfig),\n'
                    '        VMSTATE_BOOL(raw_stream_started, NikonZ72BootConfig),')
    board = replace(board, '    qdev_init_gpio_in_named(DEVICE(obj), raw_stream_frame, "raw-stream-frame", 1);', '''    qdev_init_gpio_in_named(DEVICE(obj), raw_stream_frame, "raw-stream-frame", 1);
    qdev_init_gpio_out_named(DEVICE(obj), &s->finite_enable_irq, "finite-enable", 1);
    qdev_init_gpio_out_named(DEVICE(obj), &s->finite_frame_irq, "finite-frame", 1);
    qdev_init_gpio_out_named(DEVICE(obj), &s->finite_commit_irq, "finite-commit", 1);''')
    board = replace(board, '        DEFINE_PROP_BOOL("z62-raw-stream",',
                    '        DEFINE_PROP_BOOL("z62-finite-stats", NikonZ72BootConfig, z62_finite_stats, false),\n'
                    '        DEFINE_PROP_BOOL("z62-raw-stream",')
    board = replace(board, '        qdev_connect_gpio_out_named(config, "raw-submit", 0,', '''        qdev_connect_gpio_out_named(config, "finite-enable", 0,
            qdev_get_gpio_in_named(input_config, "finite-enable", 0));
        qdev_connect_gpio_out_named(config, "finite-frame", 0,
            qdev_get_gpio_in_named(input_config, "finite-frame", 0));
        qdev_connect_gpio_out_named(config, "finite-commit", 0,
            qdev_get_gpio_in_named(input_config, "finite-commit", 0));
        qdev_connect_gpio_out_named(input_config, "finite-ready", 0,
            qdev_get_gpio_in_named(config, "input-event", 101));
        qdev_connect_gpio_out_named(input_config, "finite-complete", 0,
            qdev_get_gpio_in_named(config, "input-event", 103));
        qdev_connect_gpio_out_named(config, "raw-submit", 0,''')
    texts['nikon-z72.c'] = board
    return texts


def apply_source(source):
    source = Path(source).resolve()
    if not source.is_relative_to(WORK.resolve()):
        raise ValueError('Finite stats adapter requires independent r8 workspace')
    arm = source/'hw/arm'
    texts = render({name: (arm/name).read_bytes() for name in INPUTS})
    for name, text in texts.items():
        (arm/name).write_text(text, encoding='utf-8', newline='\n')
    for path in HEADERS:
        (arm/path.name).write_bytes(path.read_bytes())
    return identity()
