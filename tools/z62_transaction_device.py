# SPDX-License-Identifier: GPL-2.0-or-later
"""R5 transaction-linked completion; generated independent trees only."""
from pathlib import Path
import reference_updates as reference
import z62_functional_device as functional

ROOT = Path(__file__).resolve().parents[1]
VERSION = '2026.10.28-r5'
HEADER = ROOT / 'qemu/z62-transaction/nikon-z62-transaction.h'
INPUTS = {
    'nikon-z72.c': 'a948a662560b54f1b84db243bf65976125b2921f508ad3921f5b6d953405a8de',
    'nikon-z62-sensor-config.c': '80ed89ee62530ad9abad27026004d7d06d03def2ae2738486874caa657ae7779',
}


def identity():
    return {'schema': 1, 'version': VERSION, 'input_sha256': INPUTS,
            'adapter_sha256': reference.sha(Path(__file__).read_bytes()),
            'header_sha256': reference.sha(HEADER.read_bytes()),
            'base_functional_device': functional.identity(),
            'default_enabled': False, 'hypothesis': 'transaction-linked-mode2-IRQ92-bit1',
            'guest_patched': False, 'silicon_timing_verified': False}


def apply_source(source):
    source = Path(source).resolve()
    allowed = (ROOT / '.build' / ('z62-transaction-' + VERSION)).resolve()
    if not source.is_relative_to(allowed):
        raise ValueError('Transaction adapter requires its independent r5 workspace')
    arm = source / 'hw/arm'
    texts = {}
    for name, digest in INPUTS.items():
        data = (arm / name).read_bytes()
        if reference.sha(data) != digest:
            raise ValueError('Transaction input SHA mismatch: ' + name)
        texts[name] = data.decode('utf-8')
    replace = reference.replace_once
    text = texts['nikon-z62-sensor-config.c']
    text = replace(text, '#include "qemu/timer.h"', '#include "qemu/timer.h"\n#include "qapi/error.h"')
    text = replace(text, '    uint64_t frame_completions;', '''    uint64_t frame_completions;
    bool functional_raw_completion, raw_dma_level;
    uint64_t raw_source_events, raw_completions, raw_ignored, raw_coalesced;
    uint32_t transaction_reason;''')
    text = replace(text, 'static void sensor_mode2_complete(',
                   '#include "nikon-z62-transaction.h"\n\nstatic void sensor_mode2_complete(')
    text = replace(text, '    s->frame_completions = 0;', '''    s->frame_completions = 0;
    s->raw_dma_level = false;
    s->raw_source_events = s->raw_completions = 0;
    s->raw_ignored = s->raw_coalesced = 0;
    s->transaction_reason = TX_RESET;''')
    text = replace(text, '    .minimum_version_id = 6,', '''    .minimum_version_id = 6,
    .subsections = (const VMStateDescription * const[]) {
        &transaction_vmstate, NULL
    },''')
    text = replace(text, '    qdev_init_gpio_in_named(DEVICE(s), sensor_frame_end, "frame-end", 1);', '''    qdev_init_gpio_in_named(DEVICE(s), sensor_frame_end, "frame-end", 1);
    qdev_init_gpio_in_named(DEVICE(s), sensor_raw_dma_complete, "raw-dma-complete", 1);
    object_property_add_uint64_ptr(obj, "raw-source-events", &s->raw_source_events, OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(obj, "raw-completions", &s->raw_completions, OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(obj, "raw-ignored", &s->raw_ignored, OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(obj, "raw-coalesced", &s->raw_coalesced, OBJ_PROP_FLAG_READ);
    object_property_add_str(obj, "raw-completion-last-reason", transaction_reason, NULL);''')
    text = replace(text, '    static const Property properties[] = {', '''    static const Property properties[] = {
        DEFINE_PROP_BOOL("functional-raw-completion", Z62SensorConfig,
                         functional_raw_completion, false),''')
    text = replace(text, '    dc->vmsd = &sensor_config_vmstate;',
                   '    dc->vmsd = &sensor_config_vmstate;\n    dc->realize = transaction_realize;')
    board = replace(texts['nikon-z72.c'],
        '        sysbus_realize_and_unref(SYS_BUS_DEVICE(sensor_config), &error_fatal);',
        '        sysbus_realize_and_unref(SYS_BUS_DEVICE(sensor_config), &error_fatal);\n'
        '        qdev_connect_gpio_out_named(input_config, "raw-complete", 0,\n'
        '            qdev_get_gpio_in_named(sensor_config, "raw-dma-complete", 0));')
    # All fixed inputs and unique replacements validated before any write.
    (arm / 'nikon-z62-sensor-config.c').write_text(text, encoding='utf-8', newline='\n')
    (arm / 'nikon-z72.c').write_text(board, encoding='utf-8', newline='\n')
    (arm / HEADER.name).write_bytes(HEADER.read_bytes())
    return identity()
