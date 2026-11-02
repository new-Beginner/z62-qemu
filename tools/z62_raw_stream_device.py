# SPDX-License-Identifier: GPL-2.0-or-later
"""Independent r7 actual-DMA-linked channel2 frame source."""
from pathlib import Path
import reference_updates as reference

ROOT = Path(__file__).resolve().parents[1]
VERSION = '2026.10.29-r7'
WORK = ROOT / '.build' / ('z62-raw-stream-' + VERSION)
HEADER = ROOT / 'qemu/z62-raw-stream/nikon-z62-raw-stream.h'
INPUT_SHA = '3e5cd8d13cc5cc25a2d85a4cfcf04a5ec870d5f517a4856c8c3469af454f21d5'


def identity():
    return {'schema': 1, 'version': VERSION, 'input_sha256': INPUT_SHA,
            'adapter_sha256': reference.sha(Path(__file__).read_bytes()),
            'header_sha256': reference.sha(HEADER.read_bytes()),
            'default_enabled': False, 'completion': 'actual RAW DMA -> bank4 bit8 IRQ96',
            'clock': 'existing frame-sync source; functional cadence',
            'isp_implemented': False, 'metadata_implemented': False,
            'pixel_packing_verified': False, 'guest_software_patched': False}


def render(data):
    if reference.sha(data) != INPUT_SHA:
        raise ValueError('Raw stream input board SHA mismatch')
    text = data.decode('utf-8')
    replace = reference.replace_once
    text = replace(text, '    qemu_irq raw_submit_irq;', '''    qemu_irq raw_submit_irq;
    bool z62_raw_stream, raw_stream_started, raw_stream_waiting, raw_stream_completed;
    bool raw_stream_frame_level, raw_stream_dma_level;
    qemu_irq raw_stream_sensor_irq;
    uint64_t raw_stream_attempts, raw_stream_frames, raw_stream_failed;
    uint64_t raw_stream_blocked, raw_stream_unrelated;''')
    text = replace(text, '/* Z62 1020A71A decodes these command acknowledgements.',
        '#include "nikon-z62-raw-stream.h"\n\n/* Z62 1020A71A decodes these command acknowledgements.')
    text = replace(text, '    s->frame_sync_count++;', '''    raw_stream_frame(s, 0, 1);
    raw_stream_frame(s, 0, 0);
    s->frame_sync_count++;''')
    text = replace(text, '        *boot_config_value(s, 0x20068200) |= 0x79;',
        '        raw_stream_control(s, address, value);\n        *boot_config_value(s, 0x20068200) |= 0x79;')
    text = replace(text, '        *boot_config_value(s, base + 4) = *state;',
        '        *boot_config_value(s, base + 4) = *state;\n        raw_stream_control(s, address, value);')
    text = replace(text, '    *stored = value;\n    if (address == 0x200632e4',
        '    *stored = value;\n    raw_stream_control(s, address, value);\n    if (address == 0x200632e4')
    text = replace(text, '    capcom_reset(s);', '    capcom_reset(s);\n    raw_stream_reset(s);')
    text = replace(text, '    .version_id = 39,\n    .minimum_version_id = 39,',
        '    .version_id = 40,\n    .minimum_version_id = 40,')
    text = replace(text, '        VMSTATE_TIMER_PTR(capcom_timer, NikonZ72BootConfig),', '''        VMSTATE_TIMER_PTR(capcom_timer, NikonZ72BootConfig),
        VMSTATE_BOOL(raw_stream_started, NikonZ72BootConfig),
        VMSTATE_BOOL(raw_stream_waiting, NikonZ72BootConfig),
        VMSTATE_BOOL(raw_stream_completed, NikonZ72BootConfig),
        VMSTATE_BOOL(raw_stream_frame_level, NikonZ72BootConfig),
        VMSTATE_BOOL(raw_stream_dma_level, NikonZ72BootConfig),
        VMSTATE_UINT64(raw_stream_attempts, NikonZ72BootConfig),
        VMSTATE_UINT64(raw_stream_frames, NikonZ72BootConfig),
        VMSTATE_UINT64(raw_stream_failed, NikonZ72BootConfig),
        VMSTATE_UINT64(raw_stream_blocked, NikonZ72BootConfig),
        VMSTATE_UINT64(raw_stream_unrelated, NikonZ72BootConfig),''')
    text = replace(text, '    qdev_init_gpio_out_named(DEVICE(obj), &s->raw_submit_irq, "raw-submit", 1);', '''    qdev_init_gpio_out_named(DEVICE(obj), &s->raw_submit_irq, "raw-submit", 1);
    qdev_init_gpio_in_named(DEVICE(obj), raw_stream_frame, "raw-stream-frame", 1);
    qdev_init_gpio_in_named(DEVICE(obj), raw_stream_dma_done, "raw-stream-dma-done", 1);
    qdev_init_gpio_out_named(DEVICE(obj), &s->raw_stream_sensor_irq, "raw-sensor-complete", 1);
    object_property_add_bool(obj, "raw-stream-active", raw_stream_active_get, NULL);
    object_property_add_uint64_ptr(obj, "raw-stream-attempts", &s->raw_stream_attempts, OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(obj, "raw-stream-frames", &s->raw_stream_frames, OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(obj, "raw-stream-failed", &s->raw_stream_failed, OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(obj, "raw-stream-blocked", &s->raw_stream_blocked, OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(obj, "raw-stream-unrelated", &s->raw_stream_unrelated, OBJ_PROP_FLAG_READ);''')
    text = replace(text, '        DEFINE_PROP_BOOL("z62-capcom-sync", NikonZ72BootConfig, z62_capcom_sync, false),',
        '        DEFINE_PROP_BOOL("z62-raw-stream", NikonZ72BootConfig, z62_raw_stream, false),\n'
        '        DEFINE_PROP_BOOL("z62-capcom-sync", NikonZ72BootConfig, z62_capcom_sync, false),')
    text = replace(text, '            qdev_get_gpio_in_named(sensor_config, "raw-dma-complete", 0));',
        '            qdev_get_gpio_in_named(config, "raw-stream-dma-done", 0));\n'
        '        qdev_connect_gpio_out_named(config, "raw-sensor-complete", 0,\n'
        '            qdev_get_gpio_in_named(sensor_config, "raw-dma-complete", 0));')
    return text


def apply_source(source):
    source = Path(source).resolve()
    if not source.is_relative_to(WORK.resolve()):
        raise ValueError('Raw stream adapter requires its independent r7 workspace')
    path = source / 'hw/arm/nikon-z72.c'
    text = render(path.read_bytes())
    path.write_text(text, encoding='utf-8', newline='\n')
    (path.parent / HEADER.name).write_bytes(HEADER.read_bytes())
    return identity()
