"""Hash-bound r48 compound software ISP over frozen r47b sources."""
from pathlib import Path
import reference_updates as reference

ROOT=Path(__file__).resolve().parents[1]
VERSION='2026.11.02-r48'
WORK=ROOT/'.build'/('z62-grid-'+VERSION)
HEADERS=tuple(ROOT/'qemu/z62-grid'/n for n in ('nikon-z62-grid.h','nikon-z62-grid-pixels.h'))
INPUTS={
    'nikon-z72.c':'8c5d294ba12a5c4608f5f63d4bcc82745bd4bf65e3fa4ea8b650b20dc0299553',
    'nikon-z72-input-config.c':'79c19c0a348eb5dfd98c3789f4dd0780e9dd9ef74e12e4bc7ada14ddfa8190ad',
    'nikon-z62-preview.h':'ad11409bc9c9cc6eae4630620b9f4cf95e01192d8a61cae0edda7b32ac8640ba',
    'nikon-z62-continuous-stats.h':'0a948bf810903f42f30acb3fb28c2fed811c5e58ecb33518028a29068233da13'
}


def identity():
    return {'schema':1,'version':VERSION,'input_sha256':INPUTS,
        'adapter_sha256':reference.sha(Path(__file__).read_bytes()),
        'headers_sha256':{p.name:reference.sha(p.read_bytes()) for p in HEADERS},
        'default_enabled':False,'algorithm_level':'C','transport_and_irq_level':'B',
        'algorithm':'three actual LE-u16 RGB planes -> rounded equal mean -> packed12',
        'full_nikon_eleven_operators_implemented':False,'source_provenance':'private six-slot notification after actual statistics DMA',
        'software_callback_fields_used_for_success':False,'guest_software_patched':False}


def render(files):
    for name,digest in INPUTS.items():
        if reference.sha(files[name])!=digest: raise ValueError('Grid requires unchanged r47b source: '+name)
    out={n:data.decode('utf-8') for n,data in files.items()}
    replace=reference.replace_once
    board=out['nikon-z72.c']
    board=replace(board,'    bool z62_preview_results;', '''    bool z62_preview_results;
    bool z62_grid_process, grid_needs_check;
    uint8_t grid_supplied_mask, grid_level_mask;
    uint32_t grid_reason;
    uint64_t grid_source_seq, grid_checked_seq, grid_slot_epoch[6], grid_seen_epoch[6];
    uint64_t grid_groups, grid_outputs, grid_bytes, grid_rejected, grid_blocked;
    QEMUTimer *grid_timer;''')
    board=replace(board,'    .version_id = 45,\n    .minimum_version_id = 45,',
                        '    .version_id = 46,\n    .minimum_version_id = 46,')
    board=replace(board,'        VMSTATE_UINT64(preview_result_blocked, NikonZ72BootConfig),',
        '''        VMSTATE_UINT64(preview_result_blocked, NikonZ72BootConfig),
        VMSTATE_BOOL(z62_grid_process, NikonZ72BootConfig),
        VMSTATE_BOOL(grid_needs_check, NikonZ72BootConfig),
        VMSTATE_UINT8(grid_supplied_mask, NikonZ72BootConfig),
        VMSTATE_UINT8(grid_level_mask, NikonZ72BootConfig),
        VMSTATE_UINT32(grid_reason, NikonZ72BootConfig),
        VMSTATE_UINT64(grid_source_seq, NikonZ72BootConfig),
        VMSTATE_UINT64(grid_checked_seq, NikonZ72BootConfig),
        VMSTATE_UINT64_ARRAY(grid_slot_epoch, NikonZ72BootConfig, 6),
        VMSTATE_UINT64_ARRAY(grid_seen_epoch, NikonZ72BootConfig, 6),
        VMSTATE_UINT64(grid_groups, NikonZ72BootConfig),
        VMSTATE_UINT64(grid_outputs, NikonZ72BootConfig),
        VMSTATE_UINT64(grid_bytes, NikonZ72BootConfig),
        VMSTATE_UINT64(grid_rejected, NikonZ72BootConfig),
        VMSTATE_UINT64(grid_blocked, NikonZ72BootConfig),
        VMSTATE_TIMER_PTR(grid_timer, NikonZ72BootConfig),''')
    board=replace(board,'        DEFINE_PROP_BOOL("z62-preview-results", NikonZ72BootConfig, z62_preview_results, false),',
        '        DEFINE_PROP_BOOL("z62-preview-results", NikonZ72BootConfig, z62_preview_results, false),\n'
        '        DEFINE_PROP_BOOL("z62-grid-process", NikonZ72BootConfig, z62_grid_process, false),')
    board=replace(board,'static int boot_config_post_load(void *opaque, int version_id)\n{\n    NikonZ72BootConfig *s = opaque;',
        '''static int boot_config_post_load(void *opaque, int version_id)
{
    NikonZ72BootConfig *s = opaque;
    if ((s->grid_supplied_mask & ~0x3fu) || (s->grid_level_mask & ~0x3fu) ||
        s->grid_reason > 11 || s->grid_checked_seq > s->grid_source_seq) { return -EINVAL; }
    for (unsigned i=0;i<6;i++) {
        if (s->grid_seen_epoch[i] > s->grid_slot_epoch[i] ||
            s->grid_slot_epoch[i] > s->grid_source_seq ||
            (!!(s->grid_supplied_mask & (1u<<i)) != !!s->grid_slot_epoch[i])) { return -EINVAL; }
    }''')
    board=replace(board,'        qdev_connect_gpio_out_named(input_config, "finite-complete", 0,\n'
        '            qdev_get_gpio_in_named(config, "input-event", 103));',
        '        qdev_connect_gpio_out_named(input_config, "finite-complete", 0,\n'
        '            qdev_get_gpio_in_named(config, "input-event", 103));\n'
        '        for (unsigned slot=0;slot<6;slot++) {\n'
        '            qdev_connect_gpio_out_named(input_config, "z62-statistics-slot-ready", slot,\n'
        '                qdev_get_gpio_in_named(config, "z62-grid-source", slot));\n'
        '        }')
    out['nikon-z72.c']=board
    text=out['nikon-z72-input-config.c']
    text=replace(text,'    qemu_irq finite_enable_irq, finite_ready_irq, finite_complete_irq;',
        '    qemu_irq finite_enable_irq, finite_ready_irq, finite_complete_irq;\n'
        '    qemu_irq z62_statistics_slot_irq[6];')
    text=replace(text,'    qdev_init_gpio_out_named(DEVICE(obj), &s->finite_complete_irq, "finite-complete", 1);',
        '    qdev_init_gpio_out_named(DEVICE(obj), &s->finite_complete_irq, "finite-complete", 1);\n'
        '    qdev_init_gpio_out_named(DEVICE(obj), s->z62_statistics_slot_irq, "z62-statistics-slot-ready", 6);')
    out['nikon-z72-input-config.c']=text
    out['nikon-z62-continuous-stats.h']=replace(out['nikon-z62-continuous-stats.h'],
        '    s->continuous_frames++;',
        '    /* Private model provenance: all five outputs were actually written. */\n'
        '    qemu_set_irq(s->z62_statistics_slot_irq[s->continuous_index],1);\n'
        '    qemu_set_irq(s->z62_statistics_slot_irq[s->continuous_index],0);\n'
        '    s->continuous_frames++;')
    preview=out['nikon-z62-preview.h']
    preview=replace(preview,'#include "nikon-z62-preview-results.h"',
        '#include "nikon-z62-preview-results.h"\n#include "nikon-z62-grid.h"')
    preview=replace(preview,'    if(preview_unit_status(offset)) { return timer_pending(s->preview_timer) ? 3:0; }',
        '    if (z62_grid_supported(s) && offset==0x9c0) { return timer_pending(s->grid_timer) ? 3:0; }\n'
        '    if(preview_unit_status(offset)) { return timer_pending(s->preview_timer) ? 3:0; }')
    preview=replace(preview,'    NikonZ72BootConfig *s=opaque;\n    if(offset<0x100) {\n        if(offset==4',
        '    NikonZ72BootConfig *s=opaque;\n'
        '    uint32_t grid_old=offset<0x100 ? ldl_le_p(s->transfer_table+offset) : s->preview_core[offset/4];\n'
        '    if(offset<0x100) {\n        if(offset==4')
    preview=replace(preview,'        s->preview_core[offset/4]=value;\n    }\n    preview_schedule(s);',
        '        s->preview_core[offset/4]=value;\n    }\n'
        '    z62_grid_written(s,offset,grid_old,value);\n    preview_schedule(s);')
    preview=replace(preview,'    preview_results_reset(s);','    preview_results_reset(s);\n    z62_grid_reset(s);')
    preview=replace(preview,'    preview_results_qom_init(obj);','    preview_results_qom_init(obj);\n    z62_grid_init(obj);')
    preview=replace(preview,'static void preview_finalize(NikonZ72BootConfig *s)\n{',
        'static void preview_finalize(NikonZ72BootConfig *s)\n{\n'
        '    timer_del(s->grid_timer); timer_free(s->grid_timer);')
    out['nikon-z62-preview.h']=preview
    return out


def apply_source(source):
    source=Path(source).resolve()
    if not source.is_relative_to(WORK.resolve()): raise ValueError('Grid requires independent workspace')
    arm=source/'hw/arm'
    out=render({n:(arm/n).read_bytes() for n in INPUTS})
    for name,text in out.items(): (arm/name).write_text(text,encoding='utf-8',newline='\n')
    for p in HEADERS: (arm/p.name).write_bytes(p.read_bytes())
    return identity()
