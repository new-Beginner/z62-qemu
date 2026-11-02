# SPDX-License-Identifier: GPL-2.0-or-later
"""Guarded generated-source-only Z62 experimental RAW adapter."""
from pathlib import Path
import reference_updates

ROOT = Path(__file__).resolve().parents[1]
VERSION = '2026.10.28-r4'
INPUTS = {
    'nikon-z72.c': '918225b3590d1aa3251bbd598e2a7a890cf557c8dcec1959866162b01080453a',
    'nikon-z72-input-config.c': 'a0bc556c6ed4742c5749005c2a644fa3fae963bd7ec3c06312943fe500f266c4',
}
HEADER = ROOT / 'qemu/z62-functional/nikon-z62-functional-raw.h'


def identity():
    return {'version': VERSION, 'input_sha256': INPUTS,
            'adapter_sha256': reference_updates.sha(Path(__file__).read_bytes()),
            'header_sha256': reference_updates.sha(HEADER.read_bytes()),
            'packing': 'experimental-packed12-not-hardware-verified',
            'trigger': 'explicit-20068104-submit-only', 'default_enabled': False,
            'sensor_completion_source': False, 'guest_patched': False}


def apply_source(source):
    source = Path(source).resolve()
    if not source.is_relative_to((ROOT / '.build').resolve()):
        raise ValueError('Functional adapter accepts only generated .build source')
    arm = source / 'hw/arm'
    texts = {}
    for name, sha in INPUTS.items():
        data = (arm / name).read_bytes()
        if reference_updates.sha(data) != sha:
            raise ValueError('Functional input hash mismatch: ' + name)
        texts[name] = data.decode('utf-8')
    replace = reference_updates.replace_once
    text = texts['nikon-z72-input-config.c']
    text = replace(text, '#include "migration/vmstate.h"',
                   '#include "migration/vmstate.h"\n#include "system/address-spaces.h"\n#include "qapi/error.h"')
    text = replace(text, '    qemu_irq metadata_irq;\n', '''    qemu_irq metadata_irq;
    MemoryRegion *raw_root;
    AddressSpace raw_memory;
    bool functional_raw, raw_submit_level;
    uint64_t raw_accepted, raw_rejected, raw_bytes;
    uint32_t raw_reason;
    qemu_irq raw_complete;
''')
    text = replace(text, 'static void input_frame_end(',
                   '#include "nikon-z62-functional-raw.h"\n\nstatic void input_frame_end(')
    text = replace(text, '    s->metadata_completions = 0;', '''    s->metadata_completions = 0;
    s->raw_accepted = s->raw_rejected = s->raw_bytes = 0;
    s->raw_reason = RAW_RESET;
    s->raw_submit_level = false;
    qemu_set_irq(s->raw_complete, 0);''')
    text = replace(text, '    .minimum_version_id = 2,', '''    .minimum_version_id = 2,
    .subsections = (const VMStateDescription * const[]) { &raw_vmstate, NULL },''')
    text = replace(text, '    sysbus_init_mmio(SYS_BUS_DEVICE(s), &s->iomem);', '''    sysbus_init_mmio(SYS_BUS_DEVICE(s), &s->iomem);
    qdev_init_gpio_in_named(DEVICE(s), raw_submit, "raw-submit", 1);
    qdev_init_gpio_out_named(DEVICE(s), &s->raw_complete, "raw-complete", 1);
    object_property_add_uint64_ptr(obj, "raw-accepted", &s->raw_accepted, OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(obj, "raw-rejected", &s->raw_rejected, OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(obj, "raw-bytes", &s->raw_bytes, OBJ_PROP_FLAG_READ);
    object_property_add_str(obj, "raw-last-reason", raw_reason_get, NULL);''')
    text = replace(text, '    dc->vmsd = &input_config_vmstate;', '''    dc->vmsd = &input_config_vmstate;
    dc->realize = raw_realize;
    dc->unrealize = raw_unrealize;''')
    text = replace(text, '    static const Property properties[] = {', '''    static const Property properties[] = {
        DEFINE_PROP_BOOL("functional-raw", Z72InputConfig, functional_raw, false),
        DEFINE_PROP_LINK("raw-root", Z72InputConfig, raw_root, TYPE_MEMORY_REGION, MemoryRegion *),''')
    board = texts['nikon-z72.c']
    board = replace(board, '    qemu_irq sensor_submit_irq;',
                    '    qemu_irq sensor_submit_irq;\n    qemu_irq raw_submit_irq;')
    board = replace(board, '        qemu_set_irq(s->sensor_submit_irq, 1);', '''        qemu_set_irq(s->sensor_submit_irq, 1);
        qemu_set_irq(s->raw_submit_irq, 1);
        qemu_set_irq(s->raw_submit_irq, 0);''')
    board = replace(board, '    qemu_set_irq(s->sensor_submit_irq, 0);\n    qemu_set_irq(s->sensor_mode_arm_irq',
                    '    qemu_set_irq(s->sensor_submit_irq, 0);\n    qemu_set_irq(s->raw_submit_irq, 0);\n    qemu_set_irq(s->sensor_mode_arm_irq')
    board = replace(board, '    qdev_init_gpio_out_named(DEVICE(obj), &s->sensor_submit_irq, "sensor-submit", 1);',
                    '    qdev_init_gpio_out_named(DEVICE(obj), &s->sensor_submit_irq, "sensor-submit", 1);\n'
                    '    qdev_init_gpio_out_named(DEVICE(obj), &s->raw_submit_irq, "raw-submit", 1);')
    board = replace(board, '    qdev_prop_set_bit(input_config, "z62-layout", z62);',
                    '    qdev_prop_set_bit(input_config, "z62-layout", z62);\n'
                    '    object_property_set_link(OBJECT(input_config), "raw-root", OBJECT(view), &error_fatal);')
    board = replace(board, '    sysbus_realize_and_unref(SYS_BUS_DEVICE(input_config), &error_fatal);',
                    '    sysbus_realize_and_unref(SYS_BUS_DEVICE(input_config), &error_fatal);\n'
                    '    if (z62) {\n'
                    '        qdev_connect_gpio_out_named(config, "raw-submit", 0,\n'
                    '            qdev_get_gpio_in_named(input_config, "raw-submit", 0));\n    }')
    # Validate all anchors and hashes before writing any generated file.
    (arm / 'nikon-z72-input-config.c').write_text(text, encoding='utf-8', newline='\n')
    (arm / 'nikon-z72.c').write_text(board, encoding='utf-8', newline='\n')
    (arm / HEADER.name).write_bytes(HEADER.read_bytes())
    return identity()
