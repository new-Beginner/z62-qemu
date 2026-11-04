"""Independent default-off C inline MAIN readout for the observed 136-row phase."""
from pathlib import Path
import reference_updates as reference
import z62_capturework_finite_device as parent

ROOT=Path(__file__).resolve().parents[1]
VERSION='2026.11.04-r102'
WORK=ROOT/'.build'/('z62-input-readout-'+VERSION)
HEADER=ROOT/'qemu/z62-capturework/nikon-z62-input-readout.h'
INPUTS={
    'hw/arm/nikon-z72.c':'434e0c073d1daff2df23dc72fedb666c2489859258ab40cdbcb1eb7f56efe244',
    'hw/arm/nikon-z72-input-config.c':'2942949a74902646cad256705ead99f013d5c19a2029478c9c9fa15821ed34de',
    'hw/arm/nikon-z62-capturework-state.h':'501db54e1e40f4dfc435535e70ae864098864a5deab774ccc0dc0f2890c9c333',
    'hw/arm/nikon-z62-capturework-device.h':'be6dd15510c88a686723d4b216cf5e20a10c0cc19ff38ea4ca52281e33ab19f8',
}


def identity():
    return {'schema':1,'version':VERSION,'parent':parent.identity(),'input_sha256':INPUTS,
        'adapter_sha256':reference.sha(Path(__file__).read_bytes()),'header_sha256':reference.sha(HEADER.read_bytes()),
        'property':'z62-input-readout','default_enabled':False,'level':'C inline readout of supplied MAIN view',
        'physical_sensor_equivalence':False,'guest_RAW_DMA':False,'guest_software_modified':False}


def render(files):
    for name,sha in INPUTS.items():
        if reference.sha(files[name])!=sha:raise ValueError('Input readout requires frozen r98 '+name)
    out={name:data.decode('utf-8') for name,data in files.items()};replace=reference.replace_once
    name='hw/arm/nikon-z62-capturework-state.h'
    out[name]+='''
typedef struct Z62InputReadout {
    bool enabled,pending;
    Z62MainSource source;
    Z62MainLease lease;
    Z62MainMetadata output;
    QEMUTimer *timer;
    qemu_irq complete;
    uint64_t generation,accepted,completed,cancelled,rejected,bytes,sum,hash,last_bytes;
    uint32_t last_rows;
} Z62InputReadout;
'''
    name='hw/arm/nikon-z72-input-config.c'
    out[name]=replace(out[name],'    Z62CWFinite cw_finite;',
        '    Z62CWFinite cw_finite;\n    Z62InputReadout input_readout;')
    anchor='        DEFINE_PROP_BOOL("z62-capturework-finite", Z72InputConfig, cw_finite.enabled, false),'
    out[name]=replace(out[name],anchor,anchor+'\n        DEFINE_PROP_BOOL("z62-input-readout", Z72InputConfig, input_readout.enabled, false),')
    name='hw/arm/nikon-z62-capturework-device.h';header=out[name]
    header=replace(header,'static void cw_start(Z72InputConfig *s);',
        '#include "nikon-z62-input-readout.h"\nstatic void cw_start(Z72InputConfig *s);')
    header=replace(header,'    else return;\n    cw_start(s);','    else return;\n    input_readout_control(s);\n    cw_start(s);')
    header=replace(header,'    Z62CaptureWork *c=&s->cw; cw_cancel(s);',
        '    input_readout_reset(s);\n    Z62CaptureWork *c=&s->cw; cw_cancel(s);')
    anchor='    s->group.generation=1;'
    header=replace(header,anchor,anchor+'\n    s->input_readout.timer=timer_new_ns(QEMU_CLOCK_VIRTUAL,input_readout_tick,s);\n'
        '    object_property_add_str(obj,"input-readout-file",NULL,input_readout_file);\n'
        '    object_property_add_str(obj,"input-readout-status",input_readout_status,NULL);\n'
        '    qdev_init_gpio_out_named(DEVICE(obj),&s->input_readout.complete,"input-readout-complete",1);')
    header=replace(header,'    if (!s->cw.enabled) return;',
        '    if (s->input_readout.enabled && !s->cw.enabled) { error_setg(errp,"C input readout requires CW control model");return; }\n'
        '    if (!s->cw.enabled) return;')
    header=replace(header,'    Z72InputConfig *s=Z72_INPUT_CONFIG(dev); s->cw.stopping=true; cw_cancel(s);',
        '    Z72InputConfig *s=Z72_INPUT_CONFIG(dev); input_readout_reset(s); s->cw.stopping=true; cw_cancel(s);')
    header=replace(header,'{ timer_free(Z72_INPUT_CONFIG(obj)->cw.timer); }',
        '{ timer_free(Z72_INPUT_CONFIG(obj)->input_readout.timer); timer_free(Z72_INPUT_CONFIG(obj)->cw.timer); }')
    out[name]=header
    name='hw/arm/nikon-z72.c';anchor='        qdev_connect_gpio_out_named(config, "raw-sensor-complete", 0,'
    out[name]=replace(out[name],anchor,
        '        qdev_connect_gpio_out_named(input_config,"input-readout-complete",0,\n'
        '            qdev_get_gpio_in_named(sensor_config,"raw-dma-complete",0));\n'+anchor)
    out['hw/arm/'+HEADER.name]=HEADER.read_text(encoding='utf-8')
    return {name:data.encode('utf-8') for name,data in out.items()}
