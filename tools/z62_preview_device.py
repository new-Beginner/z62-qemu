"""Independent r9 functional-preview adapter, preserving the verified r8 kernel."""
from pathlib import Path
import reference_updates as reference

ROOT=Path(__file__).resolve().parents[1]
VERSION='2026.10.29-r9'
WORK=ROOT/'.build'/('z62-preview-'+VERSION)
HEADERS=tuple(ROOT/'qemu/z62-preview'/name for name in
              ('nikon-z62-preview.h','nikon-z62-preview-pixels.h'))
INPUTS={'nikon-z72.c':'ddf71f0aa606cda75f5699c62d626615f7c8bde4d00a9a5ba79d046c3301b623',
        'nikon-z62-raw-stream.h':'391edff82788be9526e38dba113ab4c3b52291a7fd6acde0ae7010fb825eb1c2'}


def identity():
    return {'schema':1,'version':VERSION,'input_sha256':INPUTS,
        'adapter_sha256':reference.sha(Path(__file__).read_bytes()),
        'headers_sha256':{p.name:reference.sha(p.read_bytes()) for p in HEADERS},
        'default_enabled':False,'algorithm':'approximate cropped RGGB12/sRGB/NV12 preview',
        'statistics_bank0_completed':False,'arbitrary_node_graphs_supported':False,
        'silicon_pixel_math_verified':False,'guest_software_patched':False}


def render(files):
    for name,expected in INPUTS.items():
        if reference.sha(files[name])!=expected: raise ValueError('Preview input SHA mismatch: '+name)
    texts={n:d.decode('utf-8') for n,d in files.items()}
    replace=reference.replace_once
    board=texts['nikon-z72.c']
    board=replace(board,'#include "nikon-z72-controller.h"',
        '#include "nikon-z72-controller.h"\n#include "nikon-z62-preview-pixels.h"')
    board=replace(board,'    bool z62_finite_stats, finite_started;', '''    bool z62_finite_stats, finite_started;
    bool z62_preview, preview_mapped, preview_source_valid, preview_flush_pending, preview_stopping;
    MemoryRegion preview_core_mr, preview_raw_mr;
    AddressSpace preview_memory;
    uint32_t preview_core[0x3000/4], preview_raw[0x10000/4], preview_source[4];
    uint32_t preview_drain_mask, preview_reason;
    uint64_t preview_source_seq, preview_last_seq, preview_attempts, preview_batches;
    uint64_t preview_outputs, preview_bytes, preview_rejected, preview_blocked;
    uint64_t preview_cancelled, preview_drains, preview_flushes;
    QEMUTimer *preview_timer, *preview_drain_timer;
    Z62PreviewPixels *preview_pixels;''')
    board=replace(board,'#include "nikon-z62-raw-stream.h"',
        'static void preview_source_notify(NikonZ72BootConfig *s);\n#include "nikon-z62-raw-stream.h"')
    board=replace(board,'static void transport_update_irq(',
        '#include "nikon-z62-preview.h"\n\nstatic void transport_update_irq(')
    board=replace(board,'    qemu_set_irq(qdev_get_gpio_in(s->intc, 102 - 32), status != 0);', '''    if (s->z62_preview && s->z62_card_detect && s->master_role) {
        status = (ldl_le_p(s->transfer_table + 0x18) & ldl_le_p(s->transfer_table + 0x0c)) |
                 (ldl_le_p(s->transfer_table + 0x1c) & ldl_le_p(s->transfer_table + 0x10)) |
                 (ldl_le_p(s->transfer_table + 0x20) & ldl_le_p(s->transfer_table + 0x14));
    }
    qemu_set_irq(qdev_get_gpio_in(s->intc, 102 - 32), status != 0);''')
    board=replace(board,'    raw_stream_reset(s);','    raw_stream_reset(s);\n    preview_reset(s);')
    board=replace(board,'    .version_id = 41,\n    .minimum_version_id = 41,',
        '    .version_id = 42,\n    .minimum_version_id = 42,')
    board=replace(board,'        VMSTATE_BOOL(finite_started, NikonZ72BootConfig),', '''        VMSTATE_BOOL(finite_started, NikonZ72BootConfig),
        VMSTATE_BOOL(preview_source_valid, NikonZ72BootConfig),
        VMSTATE_BOOL(preview_flush_pending, NikonZ72BootConfig),
        VMSTATE_BOOL(preview_stopping, NikonZ72BootConfig),
        VMSTATE_UINT32_ARRAY(preview_core, NikonZ72BootConfig, 0x3000/4),
        VMSTATE_UINT32_ARRAY(preview_raw, NikonZ72BootConfig, 0x10000/4),
        VMSTATE_UINT32_ARRAY(preview_source, NikonZ72BootConfig, 4),
        VMSTATE_UINT32(preview_drain_mask, NikonZ72BootConfig),
        VMSTATE_UINT32(preview_reason, NikonZ72BootConfig),
        VMSTATE_UINT64(preview_source_seq, NikonZ72BootConfig),
        VMSTATE_UINT64(preview_last_seq, NikonZ72BootConfig),
        VMSTATE_UINT64(preview_attempts, NikonZ72BootConfig),
        VMSTATE_UINT64(preview_batches, NikonZ72BootConfig),
        VMSTATE_UINT64(preview_outputs, NikonZ72BootConfig),
        VMSTATE_UINT64(preview_bytes, NikonZ72BootConfig),
        VMSTATE_UINT64(preview_rejected, NikonZ72BootConfig),
        VMSTATE_UINT64(preview_blocked, NikonZ72BootConfig),
        VMSTATE_UINT64(preview_cancelled, NikonZ72BootConfig),
        VMSTATE_UINT64(preview_drains, NikonZ72BootConfig),
        VMSTATE_UINT64(preview_flushes, NikonZ72BootConfig),
        VMSTATE_TIMER_PTR(preview_timer, NikonZ72BootConfig),
        VMSTATE_TIMER_PTR(preview_drain_timer, NikonZ72BootConfig),''')
    board=replace(board,'    s->frame_sync_timer = timer_new_ns(QEMU_CLOCK_VIRTUAL, frame_sync_tick, s);',
        '    preview_init(obj);\n    s->frame_sync_timer = timer_new_ns(QEMU_CLOCK_VIRTUAL, frame_sync_tick, s);')
    board=replace(board,'static void boot_config_finalize(Object *obj)\n{\n    NikonZ72BootConfig *s = NIKON_Z72_BOOT_CONFIG(obj);',
        'static void boot_config_finalize(Object *obj)\n{\n    NikonZ72BootConfig *s = NIKON_Z72_BOOT_CONFIG(obj);\n    preview_finalize(s);')
    board=replace(board,'    const char *tag = s->master_role ? "master" : "slave";',
        '    const char *tag = s->master_role ? "master" : "slave";\n    preview_realize(s, root);')
    board=replace(board,'        DEFINE_PROP_BOOL("z62-finite-stats",',
        '        DEFINE_PROP_BOOL("z62-preview", NikonZ72BootConfig, z62_preview, false),\n'
        '        DEFINE_PROP_BOOL("z62-finite-stats",')
    texts['nikon-z72.c']=board
    texts['nikon-z62-raw-stream.h']=replace(texts['nikon-z62-raw-stream.h'],
        '    s->raw_stream_frames++;','    s->raw_stream_frames++;\n    preview_source_notify(s);')
    return texts


def apply_source(source):
    source=Path(source).resolve()
    if not source.is_relative_to(WORK.resolve()): raise ValueError('Preview requires independent r9 workspace')
    arm=source/'hw/arm'
    texts=render({n:(arm/n).read_bytes() for n in INPUTS})
    for name,text in texts.items(): (arm/name).write_text(text,encoding='utf-8',newline='\n')
    for path in HEADERS: (arm/path.name).write_bytes(path.read_bytes())
    return identity()
