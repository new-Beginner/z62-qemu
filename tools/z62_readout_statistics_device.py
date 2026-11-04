"""r103 C readout input -> original finite channel1 transport, default off."""
from pathlib import Path
import reference_updates as reference
import z62_input_readout_device as parent

ROOT=Path(__file__).resolve().parents[1]
VERSION='2026.11.04-r103'
WORK=ROOT/'.build'/('z62-readout-statistics-'+VERSION)
HEADER=ROOT/'qemu/z62-capturework/nikon-z62-readout-statistics.h'
INPUTS={
    'hw/arm/nikon-z72-input-config.c':'fcafd83133c54f5c01e55d3be0f8a846112d4ee52bd885e4e8c552aeaf60a93e',
    'hw/arm/nikon-z62-capturework-state.h':'cb29b4acd4362707f594f296517e1c83547dd6d509a65cf082d1ce31a96f3ebc',
    'hw/arm/nikon-z62-input-readout.h':'672d8c3cb22ff51c94e9bb8f5a0a973cc6a886b3ac44a1671762262c09293405',
    'hw/arm/nikon-z62-capturework-device.h':'3dbe144fe846fe244adaf8e5707644958f33fc89b227912da3abb1b187c6b93c',
    'hw/arm/nikon-z62-finite-stats.h':'47fe89e172837c4c03b442a9ddb514103e8cb88e05cea60c0c916354bf5d237a',
}


def identity():
    return {'schema':1,'version':VERSION,'parent_readout':parent.identity(),'input_sha256':INPUTS,
        'adapter_sha256':reference.sha(Path(__file__).read_bytes()),'header_sha256':reference.sha(HEADER.read_bytes()),
        'property':'z62-readout-statistics','default_enabled':False,'level':'C reference finite means from completed inline input',
        'guest_software_modified':False,'physical_sensor_or_AF_equivalence':False,'new_RAW_acquisitions':False}


def render(files):
    for name,sha in INPUTS.items():
        if reference.sha(files[name])!=sha:raise ValueError('Readout statistics requires frozen r102 '+name)
    out={name:data.decode('utf-8') for name,data in files.items()};replace=reference.replace_once
    name='hw/arm/nikon-z62-capturework-state.h'
    out[name]=replace(out[name],'    uint32_t last_rows;',
        '    uint32_t last_rows;\n    bool stats_enabled,stats_valid,statistics_job;\n'
        '    uint8_t *completed_pixels;\n    Z62MainMetadata stats_latest,stats_batch;\n'
        '    uint64_t stats_serial,stats_batch_serial,stats_batches;')
    name='hw/arm/nikon-z72-input-config.c'
    out[name]=replace(out[name],'#include "nikon-z62-finite-stats.h"',
        '#include "nikon-z62-readout-statistics.h"\n#include "nikon-z62-finite-stats.h"')
    anchor='        DEFINE_PROP_BOOL("z62-input-readout", Z72InputConfig, input_readout.enabled, false),'
    out[name]=replace(out[name],anchor,anchor+'\n        DEFINE_PROP_BOOL("z62-readout-statistics", Z72InputConfig, input_readout.stats_enabled, false),')
    name='hw/arm/nikon-z62-input-readout.h';text=out[name]
    text=replace(text,'        !(c->held&1) && (c->allowed&c->running&1) && !(c->running&0x20c) &&',
        '        ((!(c->held&1) && (c->allowed&c->running&1) && !(c->running&0x20c)) || input_statistics_profile(s)) &&')
    text=replace(text,'    r->last_rows=r->lease.meta.height;r->last_bytes=bytes;r->completed++;',
        '    r->last_rows=r->lease.meta.height;r->last_bytes=bytes;r->completed++;\n    input_statistics_capture(s);')
    text=replace(text,'    r->generation=s->cw.generation;r->pending=true;r->accepted++;',
        '    r->generation=s->cw.generation;r->pending=true;r->accepted++;\n    r->statistics_job=input_statistics_phase(s);')
    text=replace(text,'    Z62InputReadout *r=&s->input_readout;input_readout_cancel(s);',
        '    input_statistics_reset(s);\n    Z62InputReadout *r=&s->input_readout;input_readout_cancel(s);')
    out[name]=text
    name='hw/arm/nikon-z62-finite-stats.h';text=out[name]
    text=replace(text,'    bool from_cw=s->cw_finite.enabled;',
        '    bool from_stats=s->input_readout.stats_enabled;\n    bool from_cw=!from_stats && s->cw_finite.enabled;')
    text=replace(text,'    if (!s->raw_root || (from_cw?(!s->cw_finite.valid || !s->cw_finite.linear):(!s->raw_accepted || !source))) {',
        '    if (!s->raw_root || (from_stats?(!s->input_readout.stats_valid || !input_statistics_phase(s)):\n'
        '        (from_cw?(!s->cw_finite.valid || !s->cw_finite.linear):(!s->raw_accepted || !source)))) {')
    text=replace(text,'    if (!finite_memory(s, source, RAW_BYTES, false)) {',
        '    if (!from_stats && !finite_memory(s, source, RAW_BYTES, false)) {')
    start=text.index('    g_autofree uint8_t *raw = g_malloc(RAW_BYTES);')
    end=text.index('    for (unsigned i = 0; i < G_N_ELEMENTS(finite_offsets); i++) {',start)
    original=text[start:end]
    text=text[:start]+'''    if (from_stats) {
        if (!input_statistics_pixels(s)) { s->finite_reason=1;return false; }
    } else {
'''+original+'    }\n'+text[end:]
    text=replace(text,'    cw_finite_select(s);',
        '    if (from_stats) input_statistics_select(s);\n    else cw_finite_select(s);')
    text=replace(text,'    bool changed = s->finite_enabled != !!level;',
        '    bool changed = s->finite_enabled != !!level;\n'
        '    if (changed && s->input_readout.stats_enabled) {\n'
        '        input_statistics_invalidate(s);\n'
        '        if (s->input_readout.pending && s->input_readout.statistics_job) input_readout_cancel(s);\n'
        '    }')
    out[name]=text
    name='hw/arm/nikon-z62-capturework-device.h';text=out[name]
    text=replace(text,'    object_property_add_str(obj,"input-readout-status",input_readout_status,NULL);',
        '    object_property_add_str(obj,"input-readout-status",input_readout_status,NULL);\n'
        '    object_property_add_str(obj,"input-readout-statistics-status",input_statistics_status,NULL);')
    text=replace(text,'    if (!s->cw.enabled) return;',
        '    if (s->input_readout.stats_enabled && (!s->input_readout.enabled || !s->functional_finite_stats)) {\n'
        '        error_setg(errp,"Readout statistics requires inline readout and finite statistics");return;\n'
        '    }\n    if (!s->cw.enabled) return;')
    out[name]=text;out['hw/arm/'+HEADER.name]=HEADER.read_text(encoding='utf-8')
    return {name:data.encode('utf-8') for name,data in out.items()}
