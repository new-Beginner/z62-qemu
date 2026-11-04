"""r104: actual four-slot CW linear cohort -> existing photo-preview input."""
from pathlib import Path
import reference_updates as reference
import z62_readout_statistics_device as parent

ROOT=Path(__file__).resolve().parents[1]
VERSION='2026.11.04-r104'
WORK=ROOT/'.build'/('z62-capturework-preview-'+VERSION)
HEADERS=tuple(ROOT/'qemu/z62-capturework'/n for n in ('nikon-z62-cw-preview-api.h','nikon-z62-cw-cohort.h','nikon-z62-cw-preview.h'))
INPUTS={
    'hw/arm/nikon-z72.c':'bc7a21c8c46d5f0362bafe522f290370d98facb3fbeba21d913200df116b82e0',
    'hw/arm/nikon-z72-input-config.c':'1cb1506265637e70e24bd93f4832c8254f7b58cd6f7297f607be04b4312e53bb',
    'hw/arm/nikon-z62-capturework-state.h':'a0c3f697e320e7115faadcdfd293bfe038f9df66eff5e19ad9cbc36066a569ea',
    'hw/arm/nikon-z62-capturework-api.h':'3274390371de22bc1837466206cb6bfc49ea498d6be3dd39c1e8b0a02517a221',
    'hw/arm/nikon-z62-capturework-device.h':'4c2049254f7b71515f292e048d3f05cdf328a2f446fb10f77ee991dadf604442',
    'hw/arm/nikon-z62-preview.h':'4306161b6816bd7a26774c6d7ef216d1718b2cdb290279c0103a0e16274c747c',
}


def identity():
    return {'schema':1,'version':VERSION,'parent':parent.identity(),'input_sha256':INPUTS,
        'adapter_sha256':reference.sha(Path(__file__).read_bytes()),
        'header_sha256':{p.name:reference.sha(p.read_bytes()) for p in HEADERS},
        'property':'z62-capturework-preview','default_enabled':False,'source':'four distinct actual CW DMA slots',
        'raw_domain':'private frozen-transfer quantized linear12','guest_encoded_RAW_preserved':True,
        'legacy_RAW_counters_modified':False,'metadata_event6_emitted':False,'physical_ISP_equivalence':False}


def render(files):
    for name,sha in INPUTS.items():
        if reference.sha(files[name])!=sha:raise ValueError('CW preview requires frozen r103 '+name)
    out={n:data.decode('utf-8') for n,data in files.items()};replace=reference.replace_once
    name='hw/arm/nikon-z62-capturework-api.h'
    out[name]=replace(out[name],'#endif','#include "nikon-z62-cw-preview-api.h"\n#endif')
    name='hw/arm/nikon-z62-capturework-state.h'
    out[name]+='''
typedef struct Z62CWCohort {
    bool enabled,valid;
    uint32_t mask,bank,address[4];
    uint64_t generation,epoch,sequence,collected,invalidated,rejected;
    uint8_t *linear[4];
    Z62MainMetadata meta[4];
    Z62RawTransfer transfer[4];
    char sha256[4][65];
    qemu_irq event[2];
} Z62CWCohort;
'''
    name='hw/arm/nikon-z72-input-config.c'
    out[name]=replace(out[name],'    Z62InputReadout input_readout;','    Z62InputReadout input_readout;\n    Z62CWCohort cw_cohort;')
    anchor='        DEFINE_PROP_BOOL("z62-readout-statistics", Z72InputConfig, input_readout.stats_enabled, false),'
    out[name]=replace(out[name],anchor,anchor+'\n        DEFINE_PROP_BOOL("z62-capturework-preview", Z72InputConfig, cw_cohort.enabled, false),')
    name='hw/arm/nikon-z62-capturework-device.h';text=out[name]
    text=replace(text,'static void cw_start(Z72InputConfig *s);','#include "nikon-z62-cw-cohort.h"\nstatic void cw_start(Z72InputConfig *s);')
    text=replace(text,'    timer_del(c->timer);','    cw_cohort_cancel(s);\n    timer_del(c->timer);')
    text=replace(text,'    cw_stats_publish(s,task);','    bool cohort_ready=cw_cohort_collect(s,task);\n    cw_stats_publish(s,task);')
    text=replace(text,'    for (unsigned i=0;i<3 && c->generation==generation;i++) qemu_irq_pulse(c->complete[i]);',
        '    for (unsigned i=0;i<3 && c->generation==generation;i++) qemu_irq_pulse(c->complete[i]);\n'
        '    if (cohort_ready && c->generation==generation) qemu_irq_pulse(s->cw_cohort.event[0]);')
    text=replace(text,'    task->statistics_bridge=s->cw_stats.enabled || s->cw_finite.enabled;',
        '    task->statistics_bridge=s->cw_stats.enabled || s->cw_finite.enabled || s->cw_cohort.enabled;')
    text=replace(text,'    c->completed=c->rejected=c->cancelled=c->blocked=c->bytes=0; c->reason=CW_RESET;',
        '    c->completed=c->rejected=c->cancelled=c->blocked=c->bytes=0; c->reason=CW_RESET;\n'
        '    s->cw_cohort.sequence=s->cw_cohort.collected=s->cw_cohort.invalidated=s->cw_cohort.rejected=0;\n'
        '    s->cw_cohort.generation=s->cw_cohort.epoch=s->cw_cohort.bank=0;')
    text=replace(text,'    s->group.generation=1;','    s->group.generation=1;\n'
        '    object_property_add_str(obj,"capturework-cohort-status",cw_cohort_status,NULL);\n'
        '    qdev_init_gpio_out_named(DEVICE(obj),s->cw_cohort.event,"capturework-cohort",2);')
    text=replace(text,'    if (!s->cw.enabled) return;',
        '    if (s->cw_cohort.enabled && !s->cw.enabled) {error_setg(errp,"CW preview source requires CW backend");return;}\n'
        '    if (!s->cw.enabled) return;')
    out[name]=text
    name='hw/arm/nikon-z72.c';text=out[name]
    text=replace(text,'    bool z62_preview, preview_mapped, preview_source_valid, preview_flush_pending, preview_stopping;',
        '    bool z62_preview, preview_mapped, preview_source_valid, preview_flush_pending, preview_stopping;\n    Z62CWPreviewCache cw_preview;')
    anchor='        const unsigned events[]={3,4,135,96};'
    text=replace(text,anchor,anchor+'\n        for (unsigned i=0;i<2;i++) qdev_connect_gpio_out_named(input_config,"capturework-cohort",i,\n'
        '            qdev_get_gpio_in_named(config,"capturework-cohort",i));')
    out[name]=text
    name='hw/arm/nikon-z62-preview.h';text=out[name]
    text=replace(text,'static bool preview_ready(NikonZ72BootConfig *s)',
        '#include "nikon-z62-cw-preview.h"\n\nstatic bool preview_ready(NikonZ72BootConfig *s)')
    text=replace(text,'    uint8_t word[4], descriptors[16];','    cw_preview_discard(s);\n    uint8_t word[4], descriptors[16];')
    text=replace(text,'        video_tick(s); return;','        if (s->cw_preview.owns) { s->preview_reason=2;s->preview_rejected++;s->preview_last_seq=s->preview_source_seq;return; }\n'
        '        video_tick(s); return;')
    text=replace(text,'        if(address_space_read(&s->preview_memory,src[frame],MEMTXATTRS_UNSPECIFIED,raw,Z62_PREVIEW_RAW_BYTES)!=MEMTX_OK) { goto rejected; }',
        '        if(!cw_preview_read(s,src[frame],raw,Z62_PREVIEW_RAW_BYTES)) { goto rejected; }')
    text=replace(text,'    output_lineage_reset(s);','    cw_preview_reset(s);\n    output_lineage_reset(s);')
    text=replace(text,'    output_lineage_init(obj);','    output_lineage_init(obj);\n'
        '    object_property_add_str(obj,"capturework-preview-status",cw_preview_status,NULL);\n'
        '    qdev_init_gpio_in_named(DEVICE(obj),cw_preview_event,"capturework-cohort",2);')
    text=replace(text,'    timer_del(s->paired_ingress_timer); timer_free(s->paired_ingress_timer);',
        '    cw_preview_discard(s);\n    timer_del(s->paired_ingress_timer); timer_free(s->paired_ingress_timer);')
    out[name]=text
    for path in HEADERS:out['hw/arm/'+path.name]=path.read_text(encoding='utf-8')
    return {n:data.encode('utf-8') for n,data in out.items()}
