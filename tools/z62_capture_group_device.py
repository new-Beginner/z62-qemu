"""Independent r93 unit20 numerical/DMA model on immutable r92.

No ready shortcut or replacement curve. Zero/erased coefficient resources
remain explicit rejection. Reference wire/operator: nightglasses GPL source.
"""
from pathlib import Path
import reference_updates as reference
import z62_capturework_statistics_device as parent

ROOT=Path(__file__).resolve().parents[1]
VERSION='2026.11.04-r93'
WORK=ROOT/'.build'/('z62-capture-group-'+VERSION)
HEADERS=('nikon-z62-group-pixels.h','nikon-z62-group-device.h')
DIRECTORY=ROOT/'qemu/z62-capturework'
INPUTS={
    'hw/arm/nikon-z72.c':'b0a2bae1d34cc17a1bcd74a54d6d960a8cc705cd03ea072a97dbd168e597f989',
    'hw/arm/nikon-z72-input-config.c':'f4db696fb9e3ae96c8f9f8d596ba24ff76924627e60a09cf36bfe2f74323ea80',
    'hw/arm/nikon-z62-capturework-state.h':'20685bea634ed4b90613a392c5dcb4bba59dcbba357861925fe6f05a318a0ea4',
    'hw/arm/nikon-z62-capturework-device.h':'49847c3dccb6062878d01f0dd0faf4fa034cb9286fec9dcda4f8f9c0ac220668',
}


def identity():
    return {'schema':1,'version':VERSION,'input_sha256':INPUTS,'parent_statistics':parent.identity(),
        'adapter_sha256':reference.sha(Path(__file__).read_bytes()),
        'headers_sha256':{n:reference.sha((DIRECTORY/n).read_bytes()) for n in HEADERS},
        'default_enabled':False,'property':'z62-capture-group','event':96,'unit':0x20,
        'selected_commit':0x10,'input':'explicit immutable MAIN linear16',
        'reference':'nightglasses/z7ii-qemu@0e53ea5a6d4f3fc635d63c195a92e943370ac5e9',
        'zero_curve_or_coefficients_rejected':True,'physical_AF_or_ISP_equivalence':False,
        'guest_software_modified':False,'complete_snapshot_supported':False}


def render(files):
    for name,expected in INPUTS.items():
        if reference.sha(files[name])!=expected: raise ValueError('Group requires frozen r92 '+name)
    out={name:data.decode('utf-8') for name,data in files.items()}; replace=reference.replace_once
    name='hw/arm/nikon-z62-capturework-state.h'; state=out[name]
    state=replace(state,'typedef struct Z62CWTask {','''#include "nikon-z62-group-pixels.h"
typedef struct Z62CWGroupJob {
    Z62GroupPixels pixels;
    uint64_t generation;
    uint32_t bank,cursor,address[3],results[8];
    bool success;
} Z62CWGroupJob;

typedef struct Z62CWTask {''')
    state=replace(state,'    uint8_t *statistics_linear;','    uint8_t *statistics_linear;\n    Z62CWGroupJob *group;')
    state=replace(state,'    qemu_irq complete[3];','    qemu_irq complete[4];')
    state+='''
typedef struct Z62CWGroup {
    bool enabled,valid;
    uint32_t profile[Z62_GROUP_WORDS],held,allowed,running,cursor,pending,reason;
    uint64_t generation,completed,rejected,cancelled,blocked,bytes;
    Z62MainMetadata meta;
    uint32_t last_cursor,last_bank,last_address[3],last_size[3];
} Z62CWGroup;
'''
    out[name]=state
    name='hw/arm/nikon-z72-input-config.c'; source=out[name]
    source=replace(source,'    Z62CWStatistics cw_stats;','    Z62CWStatistics cw_stats;\n    Z62CWGroup group;')
    source=replace(source,'#include "nikon-z62-capturework-device.h"',
        '#include "nikon-z62-group-device.h"\n#include "nikon-z62-capturework-device.h"')
    anchor='        DEFINE_PROP_BOOL("z62-capturework-statistics", Z72InputConfig, cw_stats.enabled, false),'
    source=replace(source,anchor,anchor+'\n        DEFINE_PROP_BOOL("z62-capture-group", Z72InputConfig, group.enabled, false),')
    out[name]=source
    name='hw/arm/nikon-z62-capturework-device.h'; header=out[name]
    header=replace(header,'    g_free(task->statistics_linear);','    g_free(task->group);\n    g_free(task->statistics_linear);')
    header=replace(header,'    timer_del(c->timer);','    group_cancel(s);\n    timer_del(c->timer);')
    header=replace(header,'    return z62_capturework_pixels_pack(&task->pixels,task->input,task->lease.meta.bytes,\n'
        '        task->packed,task->packed_bytes)==Z62_CW_PIXELS_OK?cw_stats_compute(task):-1;',
        '    int result=z62_capturework_pixels_pack(&task->pixels,task->input,task->lease.meta.bytes,\n'
        '        task->packed,task->packed_bytes)==Z62_CW_PIXELS_OK?cw_stats_compute(task):-1;\n'
        '    if (!result) group_compute_owned(task);\n    return result;')
    header=replace(header,'    cw_stats_publish(s,task);','    group_publish(s,task);\n    cw_stats_publish(s,task);')
    header=replace(header,'    /* Private data for off-BQL compute;',
        '    group_admit(s,task);\n    /* Private data for off-BQL compute;')
    header=replace(header,'    if (address==0x20068100 || address==0x20068104) cw_commit(s,value);',
        '    group_control(s,address,value);\n    if (address==0x20068100 || address==0x20068104) cw_commit(s,value);')
    header=replace(header,'    z62_main_source_reset(&c->source);','    z62_main_source_reset(&c->source);\n    group_reset(s);')
    header=replace(header,'    for (unsigned i=0;i<3;i++) qemu_set_irq(c->complete[i],0);',
        '    for (unsigned i=0;i<4;i++) qemu_set_irq(c->complete[i],0);')
    header=replace(header,'    s->cw.generation=1;','    s->group.generation=1;\n    s->cw.generation=1;')
    header=replace(header,'    qdev_init_gpio_out_named(DEVICE(obj),s->cw.complete,"capturework-complete",3);',
        '    object_property_add_str(obj,"capture-group-status",group_status,NULL);\n'
        '    qdev_init_gpio_out_named(DEVICE(obj),s->cw.complete,"capturework-complete",4);')
    header=replace(header,'    if (!s->cw.enabled) return;',
        '    if (s->group.enabled && !s->cw.enabled) { error_setg(errp,"Capture group requires explicit CW MAIN"); return; }\n'
        '    if (!s->cw.enabled) return;')
    out[name]=header
    name='hw/arm/nikon-z72.c'; board=out[name]
    board=replace(board,'        const unsigned events[]={3,4,135};\n        for (unsigned i=0;i<3;i++)',
        '        const unsigned events[]={3,4,135,96};\n        for (unsigned i=0;i<4;i++)')
    out[name]=board
    for name in HEADERS: out['hw/arm/'+name]=(DIRECTORY/name).read_text(encoding='utf-8')
    return {name:data.encode('utf-8') for name,data in out.items()}
