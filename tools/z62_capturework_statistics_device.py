"""Default-off r92 bridge from real CW DMA to five continuous statistics planes.

Preserves immutable r91 sources. Encoded guest RAW remains untouched; the
private linear12 view comes from the task's frozen quantized transfer.
"""
from pathlib import Path
import reference_updates as reference
import z62_capturework_policy_device as parent

ROOT=Path(__file__).resolve().parents[1]
VERSION='2026.11.04-r92'
WORK=ROOT/'.build'/('z62-capturework-statistics-'+VERSION)
HEADER=ROOT/'qemu/z62-capturework/nikon-z62-capturework-statistics.h'
INPUTS={
    'hw/arm/nikon-z72-input-config.c':'9d6def4bd00c8b9119a568b38816ccac55e6a19329f65d314d4d22183df6a573',
    'hw/arm/nikon-z62-capturework-device.h':'005de1c6109b970d62c06a83385807cfc2fc3490e067949649b28de426ab5429',
    'hw/arm/nikon-z62-capturework-state.h':'d481c7c73b946f1ba333a475a928cc0f85ea929eb71f1a44ecda6f1e64675641',
    'hw/arm/nikon-z62-continuous-stats.h':'b8847ab59a3d2ad681fe64184ea14054ae55ca837bb1d1fc74924ea7f027f88d',
}


def identity():
    return {'schema':1,'version':VERSION,'input_sha256':INPUTS,
        'adapter_sha256':reference.sha(Path(__file__).read_bytes()),
        'header_sha256':reference.sha(HEADER.read_bytes()),'parent_policy':parent.identity(),
        'property':'z62-capturework-statistics','default_enabled':False,
        'source':'actual completed CaptureWork DMA with frozen transfer',
        'view':'quantized midpoint linear12','guest_encoded_RAW_modified':False,
        'legacy_RAW_counters_modified':False,'physical_ISP_equivalence':False,
        'complete_snapshot_supported':False,'preview_integrated':False}


def render(files):
    for name,expected in INPUTS.items():
        if reference.sha(files[name])!=expected: raise ValueError('Statistics bridge requires frozen r91 '+name)
    out={name:data.decode('utf-8') for name,data in files.items()}; replace=reference.replace_once
    name='hw/arm/nikon-z62-capturework-state.h'; state=out[name]
    state=replace(state,'    uint8_t *input, *packed;',
        '    bool statistics_bridge;\n    uint8_t *statistics_linear;\n    uint8_t *input, *packed;')
    state+='''
typedef struct Z62CWStatistics {
    bool enabled,pending;
    uint8_t *linear;
    uint64_t generation,published,consumed,invalidated;
    Z62MainMetadata meta;
    Z62RawTransfer transfer;
    uint32_t address,bank,slot,statistics_slot;
} Z62CWStatistics;
'''
    out[name]=state
    name='hw/arm/nikon-z72-input-config.c'; source=out[name]
    source=replace(source,'    Z62CaptureWork cw;','    Z62CaptureWork cw;\n    Z62CWStatistics cw_stats;')
    source=replace(source,'#include "nikon-z62-continuous-stats.h"',
        '#include "nikon-z62-capturework-statistics.h"\n#include "nikon-z62-continuous-stats.h"')
    anchor='        DEFINE_PROP_BOOL("z62-capturework-policy0", Z72InputConfig, cw.external_policy0, false),'
    source=replace(source,anchor,anchor+'\n        DEFINE_PROP_BOOL("z62-capturework-statistics", Z72InputConfig, cw_stats.enabled, false),')
    out[name]=source
    name='hw/arm/nikon-z62-capturework-device.h'; header=out[name]
    header=replace(header,'    g_free(task->input); g_free(task->packed); g_free(task);',
        '    g_free(task->statistics_linear);\n    g_free(task->input); g_free(task->packed); g_free(task);')
    header=replace(header,'    timer_del(c->timer);','    timer_del(c->timer);\n    cw_stats_invalidate(s);')
    header=replace(header,'        task->packed,task->packed_bytes)==Z62_CW_PIXELS_OK?0:-1;',
        '        task->packed,task->packed_bytes)==Z62_CW_PIXELS_OK?cw_stats_compute(task):-1;')
    header=replace(header,'    c->cursor=(task->slot+1)%(task->profile.buffers[7]+1);',
        '    cw_stats_publish(s,task);\n    c->cursor=(task->slot+1)%(task->profile.buffers[7]+1);')
    anchor='    if (c->pending_front || c->pending_raw) { c->reason=CW_BACKPRESSURE; c->blocked++; return; }'
    header=replace(header,anchor,anchor+'\n    if (s->cw_stats.enabled && s->cw_stats.pending) { c->reason=CW_BACKPRESSURE; c->blocked++; return; }')
    header=replace(header,'    task->owner=s; task->generation=c->generation; task->profile=c->profile;',
        '    task->owner=s; task->generation=c->generation; task->profile=c->profile;\n    task->statistics_bridge=s->cw_stats.enabled;')
    header=replace(header,'    if (!c->enabled || c->stopping || c->source.leased || strlen(path)>4096 ||',
        '    if (!c->enabled || c->stopping || c->source.leased ||\n        (s->cw_stats.enabled && s->cw_stats.pending) || strlen(path)>4096 ||')
    header=replace(header,'    object_property_add_str(obj,"capturework-status",cw_status_get,NULL);',
        '    object_property_add_str(obj,"capturework-status",cw_status_get,NULL);\n'
        '    object_property_add_str(obj,"capturework-statistics-status",cw_stats_status,NULL);')
    header=replace(header,'    z62_main_source_reset(&c->source);',
        '    z62_main_source_reset(&c->source);\n'
        '    bool bridge_enabled=s->cw_stats.enabled;\n'
        '    memset(&s->cw_stats,0,sizeof(s->cw_stats)); s->cw_stats.enabled=bridge_enabled;')
    header=replace(header,'    if (!s->cw.enabled) return;',
        '    if (s->cw_stats.enabled && (!s->cw.enabled || !s->functional_continuous_stats)) {\n'
        '        error_setg(errp,"CW statistics requires CaptureWork and continuous statistics"); return;\n'
        '    }\n    if (!s->cw.enabled) return;')
    out[name]=header
    name='hw/arm/nikon-z62-continuous-stats.h'; stats=out[name]
    stats=replace(stats,'    if (s->continuous_enabled != !!level) {',
        '    if (s->continuous_enabled != !!level) {\n        if (s->cw_stats.enabled) cw_stats_invalidate(s);')
    stats=replace(stats,'    if (!s->raw_accepted || !s->continuous_source) { s->continuous_reason=1; return; }\n'
        '    if (s->raw_accepted == s->continuous_seen_raw) { return; }',
        '    bool from_cw=s->cw_stats.enabled;\n'
        '    if (from_cw ? !cw_stats_ready(s) : (!s->raw_accepted || !s->continuous_source)) { s->continuous_reason=1; return; }\n'
        '    if (!from_cw && s->raw_accepted == s->continuous_seen_raw) { return; }')
    stats=replace(stats,'    s->continuous_seen_raw=s->raw_accepted;\n    uint64_t source=s->continuous_source;\n'
        '    if (!s->raw_accepted || !source || !s->raw_root)',
        '    if (!from_cw) s->continuous_seen_raw=s->raw_accepted;\n'
        '    uint64_t source=from_cw?s->cw_stats.address:s->continuous_source;\n'
        '    if ((!from_cw && !s->raw_accepted) || !source || !s->raw_root)')
    stats=replace(stats,'    if (address_space_read(&s->raw_memory,source,MEMTXATTRS_UNSPECIFIED,raw,Z62_STATS_RAW_BYTES) != MEMTX_OK ||\n'
        '        !z62_statistics_calculate(raw,Z62_STATS_RAW_BYTES,&s->continuous_pixels)) {',
        '    bool read_ok=true;\n'
        '    if (from_cw) memcpy(raw,s->cw_stats.linear,Z62_STATS_RAW_BYTES);\n'
        '    else read_ok=address_space_read(&s->raw_memory,source,MEMTXATTRS_UNSPECIFIED,raw,Z62_STATS_RAW_BYTES)==MEMTX_OK;\n'
        '    if (!read_ok || !z62_statistics_calculate(raw,Z62_STATS_RAW_BYTES,&s->continuous_pixels)) {')
    stats=replace(stats,'    /* Private model provenance: all five outputs were actually written. */',
        '    if (from_cw) cw_stats_consumed(s);\n    /* Private model provenance: all five outputs were actually written. */')
    out[name]=stats
    out['hw/arm/'+HEADER.name]=HEADER.read_text(encoding='utf-8')
    return {name:text.encode('utf-8') for name,text in out.items()}
