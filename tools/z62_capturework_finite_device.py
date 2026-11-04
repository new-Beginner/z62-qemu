"""Default-off r98 retained CW image -> finite scalar sample source.

Keeps r93 immutable. Separate image-source ownership outlives acquisition stop;
whole reset/unrealize frees it. Finite samples retain the same source identity.
"""
from pathlib import Path
import reference_updates as reference
import z62_capture_group_device as parent

ROOT=Path(__file__).resolve().parents[1]
VERSION='2026.11.04-r98'
WORK=ROOT/'.build'/('z62-capturework-finite-'+VERSION)
HEADER=ROOT/'qemu/z62-capturework/nikon-z62-capturework-finite.h'
INPUTS={
    'hw/arm/nikon-z72-input-config.c':'99fff00276c50cbd201c1c1d6e49cf6d3f752f4d92bc9e9b1cdab92f7072425f',
    'hw/arm/nikon-z62-capturework-state.h':'e22efb8c12a5587db3b7bae82b1e1dac91159236c4c83e09b3a57caa0d11a1e8',
    'hw/arm/nikon-z62-capturework-device.h':'4e864acf48ed1ab38ffc7b775b143a02f7584d3882de28b8e1c6b01066eb3d11',
    'hw/arm/nikon-z62-finite-stats.h':'3b0020322115afcb4cef4fad6a3ae261c316ed474e5e472a6625127810a69a99',
}


def identity():
    return {'schema':1,'version':VERSION,'input_sha256':INPUTS,'parent_group':parent.identity(),
        'adapter_sha256':reference.sha(Path(__file__).read_bytes()),'header_sha256':reference.sha(HEADER.read_bytes()),
        'property':'z62-capturework-finite','default_enabled':False,'source':'actually completed CW DMA',
        'sampling_model':'existing finite sampling of one retained image, not fresh acquisitions',
        'guest_software_modified':False,'legacy_RAW_counters_modified':False,'physical_ISP_equivalence':False}


def render(files):
    for name,sha in INPUTS.items():
        if reference.sha(files[name])!=sha:raise ValueError('Finite source requires frozen r93 '+name)
    out={n:b.decode('utf-8') for n,b in files.items()};replace=reference.replace_once
    name='hw/arm/nikon-z62-capturework-state.h';state=out[name]
    state+='''
typedef struct Z62CWFinite {
    bool enabled,valid;
    uint8_t *linear;
    Z62MainMetadata meta,batch_meta;
    Z62RawTransfer transfer;
    uint64_t captured,source_cw_generation,batch_serial,batches_prepared;
    uint32_t address,bank,slot;
} Z62CWFinite;
''';out[name]=state
    name='hw/arm/nikon-z72-input-config.c';source=out[name]
    source=replace(source,'    Z62CWGroup group;','    Z62CWGroup group;\n    Z62CWFinite cw_finite;')
    source=replace(source,'#include "nikon-z62-finite-stats.h"',
        '#include "nikon-z62-capturework-finite.h"\n#include "nikon-z62-finite-stats.h"')
    anchor='        DEFINE_PROP_BOOL("z62-capture-group", Z72InputConfig, group.enabled, false),'
    source=replace(source,anchor,anchor+'\n        DEFINE_PROP_BOOL("z62-capturework-finite", Z72InputConfig, cw_finite.enabled, false),')
    out[name]=source
    name='hw/arm/nikon-z62-capturework-device.h';header=out[name]
    header=replace(header,'    group_publish(s,task);','    cw_finite_capture(s,task);\n    group_publish(s,task);')
    header=replace(header,'    task->statistics_bridge=s->cw_stats.enabled;',
        '    task->statistics_bridge=s->cw_stats.enabled || s->cw_finite.enabled;')
    header=replace(header,'    z62_main_source_reset(&c->source);','    cw_finite_reset(s);\n    z62_main_source_reset(&c->source);')
    header=replace(header,'    object_property_add_str(obj,"capture-group-status",group_status,NULL);',
        '    object_property_add_str(obj,"capture-group-status",group_status,NULL);\n'
        '    object_property_add_str(obj,"capturework-finite-status",cw_finite_status,NULL);')
    header=replace(header,'    if (!s->cw.enabled) return;',
        '    if (s->cw_finite.enabled && (!s->cw.enabled || !s->functional_finite_stats)) {\n'
        '        error_setg(errp,"Retained finite source needs CW and finite statistics"); return;\n'
        '    }\n    if (!s->cw.enabled) return;')
    header=replace(header,'    g_clear_pointer(&s->cw.source.pixels,g_free); raw_unrealize(dev);',
        '    cw_finite_reset(s);\n    g_clear_pointer(&s->cw.source.pixels,g_free); raw_unrealize(dev);')
    out[name]=header
    name='hw/arm/nikon-z62-finite-stats.h';finite=out[name]
    finite=replace(finite,'    if (!s->raw_accepted || !s->finite_source || !s->raw_root) {',
        '    bool from_cw=s->cw_finite.enabled;\n'
        '    uint64_t source=from_cw?s->cw_finite.address:s->finite_source;\n'
        '    if (!s->raw_root || (from_cw?(!s->cw_finite.valid || !s->cw_finite.linear):(!s->raw_accepted || !source))) {')
    finite=replace(finite,'finite_memory(s, s->finite_source, RAW_BYTES, false)',
        'finite_memory(s, source, RAW_BYTES, false)')
    finite=replace(finite,'        if (!finite_memory(s, address, FINITE_BYTES, true)) {',
        '        if ((from_cw && cw_finite_overlap(s,address,FINITE_BYTES)) ||\n'
        '            !finite_memory(s, address, FINITE_BYTES, true)) {')
    finite=replace(finite,'    if (address_space_read(&s->raw_memory, s->finite_source, MEMTXATTRS_UNSPECIFIED,\n'
        '                           raw, RAW_BYTES) != MEMTX_OK) {',
        '    bool read_ok=true;\n    if (from_cw) memcpy(raw,s->cw_finite.linear,RAW_BYTES);\n'
        '    else read_ok=address_space_read(&s->raw_memory,source,MEMTXATTRS_UNSPECIFIED,raw,RAW_BYTES)==MEMTX_OK;\n'
        '    if (!read_ok) {')
    finite=replace(finite,'    s->finite_index = 0;\n    s->finite_active = true;',
        '    cw_finite_select(s);\n    s->finite_index = 0;\n    s->finite_active = true;')
    out[name]=finite;out['hw/arm/'+HEADER.name]=HEADER.read_text(encoding='utf-8')
    return {n:b.encode('utf-8') for n,b in out.items()}
