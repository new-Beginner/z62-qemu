"""Hash-bound r18 continuous five-output statistics extension over frozen r17."""
from pathlib import Path
import reference_updates as reference

ROOT = Path(__file__).resolve().parents[1]
VERSION = '2026.10.29-r18'
WORK = ROOT / '.build' / ('z62-continuous-stats-' + VERSION)
HEADERS = tuple(ROOT / 'qemu/z62-continuous-stats' / name for name in
                ('nikon-z62-statistics-pixels.h', 'nikon-z62-continuous-stats.h'))
INPUTS = {
    'nikon-z72-input-config.c': '85871717bce4d7327b397ce62fd0910ea48a8028b382e410fddd6ba154b1e6dd',
    'nikon-z62-functional-raw.h': 'f090e572b070a7d1d24c629a0c77ca180518ebaedc5e1b3b5ecbc0ac9e9b7d0c',
}


def identity():
    return {'schema': 1, 'version': VERSION, 'input_sha256': INPUTS,
            'adapter_sha256': reference.sha(Path(__file__).read_bytes()),
            'headers_sha256': {p.name: reference.sha(p.read_bytes()) for p in HEADERS},
            'default_enabled': False, 'slots': 6,
            'layout': '30x20 three u32 sums/count; 30x20 u16 scalar; 3x60x40 u16 planes',
            'arithmetic_hypothesis': 'proportional full-RAW CFA regional sums and means',
            'sensor_crop_threshold_calibration_modeled': False,
            'sample_event': 101, 'batch_event': 103,
            'guest_software_patched': False, 'photo_capture_verified': False}


def render(files):
    for name, expected in INPUTS.items():
        if reference.sha(files[name]) != expected:
            raise ValueError('Continuous statistics require frozen r17 input: ' + name)
    texts = {name: data.decode('utf-8') for name, data in files.items()}
    replace = reference.replace_once
    text = texts['nikon-z72-input-config.c']
    text = replace(text, '#include "migration/vmstate.h"',
                   '#include "migration/vmstate.h"\n#include "nikon-z62-statistics-pixels.h"')
    text = replace(text, '    qemu_irq finite_enable_irq, finite_ready_irq, finite_complete_irq;',
                   '''    qemu_irq finite_enable_irq, finite_ready_irq, finite_complete_irq;
    bool functional_continuous_stats, continuous_enabled, continuous_active;
    bool continuous_clock_level, continuous_rearm;
    uint32_t continuous_source, continuous_index, continuous_reason, continuous_config[73];
    uint64_t continuous_seen_raw, continuous_attempts, continuous_frames, continuous_batches;
    uint64_t continuous_rejected, continuous_bytes, continuous_blocked;
    Z62StatisticsPixels continuous_pixels;''')
    text = replace(text, '#include "nikon-z62-finite-stats.h"',
                   '#include "nikon-z62-finite-stats.h"\n#include "nikon-z62-continuous-stats.h"')
    text = replace(text, '    finite_reset(s);', '    finite_reset(s);\n    continuous_reset(s);')
    text = replace(text, '{ &raw_vmstate, &finite_vmstate, NULL }',
                   '{ &raw_vmstate, &finite_vmstate, &continuous_vmstate, NULL }')
    for old, new, pin in (('finite_enable', 'continuous_enable', 'finite-enable'),
                          ('finite_commit', 'continuous_commit', 'finite-commit'),
                          ('finite_frame', 'continuous_frame', 'finite-frame')):
        text = replace(text, f'qdev_init_gpio_in_named(DEVICE(obj), {old}, "{pin}", 1);',
                       f'qdev_init_gpio_in_named(DEVICE(obj), {new}, "{pin}", 1);')
    properties = '\n'.join('    object_property_add_uint64_ptr(obj, "continuous-' + name + '", &s->continuous_' +
                           name + ', OBJ_PROP_FLAG_READ);' for name in
                           ('attempts', 'frames', 'batches', 'rejected', 'bytes', 'blocked'))
    properties += '\n    object_property_add_uint32_ptr(obj, "continuous-index", &s->continuous_index, OBJ_PROP_FLAG_READ);'
    properties += '\n    object_property_add_uint32_ptr(obj, "continuous-source", &s->continuous_source, OBJ_PROP_FLAG_READ);'
    properties += '\n    object_property_add_str(obj, "continuous-reason", continuous_reason_get, NULL);'
    text = replace(text, '    object_property_add_str(obj, "finite-reason", finite_reason_get, NULL);',
                   '    object_property_add_str(obj, "finite-reason", finite_reason_get, NULL);\n' + properties)
    text = replace(text, '        DEFINE_PROP_BOOL("functional-finite-stats",',
                   '        DEFINE_PROP_BOOL("functional-continuous-stats", Z72InputConfig, functional_continuous_stats, false),\n'
                   '        DEFINE_PROP_BOOL("functional-finite-stats",')
    texts['nikon-z72-input-config.c'] = text
    texts['nikon-z62-functional-raw.h'] = replace(texts['nikon-z62-functional-raw.h'],
        '    s->finite_source = dst[0]; /* actual successful DMA source */',
        '    s->finite_source = dst[0]; /* actual successful DMA source */\n'
        '    s->continuous_source = dst[0]; /* same successful transaction, independent lifecycle */')
    return texts


def apply_source(source):
    source = Path(source).resolve()
    if not source.is_relative_to(WORK.resolve()):
        raise ValueError('Continuous statistics require independent r18 workspace')
    arm = source / 'hw/arm'
    for name, text in render({n: (arm/n).read_bytes() for n in INPUTS}).items():
        (arm/name).write_text(text, encoding='utf-8', newline='\n')
    for path in HEADERS:
        (arm/path.name).write_bytes(path.read_bytes())
    return identity()
