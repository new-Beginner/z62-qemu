"""Independent default-off r89 layer on frozen r69, never an in-place patch."""
from pathlib import Path
import reference_updates as reference

ROOT=Path(__file__).resolve().parents[1]
VERSION='2026.11.04-r89'
WORK=ROOT/'.build'/('z62-capturework-'+VERSION)
DIRECTORY=ROOT/'qemu/z62-capturework'
INPUTS={
    'hw/arm/nikon-z72.c':'7e2ea3f0fa8a110c4b40663abcd7cf019ebb5c6cba4867d5c2cd54e0e1a5402f',
    'hw/arm/nikon-z72-input-config.c':'66be749b0d007dfe761795db48412651cab9aa243af419b8db0f31d1904aba74',
    'hw/arm/nikon-z62-functional-raw.h':'bbe073269133fd7cf3418dce68daa013fafdcef6c6415325cf2c1593a8a3376b',
}
HEADERS=('nikon-z62-capturework-api.h','nikon-z62-capturework-state.h','nikon-z62-capturework-device.h',
         'nikon-z62-main-source.h','nikon-z62-capturework-pixels.h','nikon-z62-raw-transfer.h')


def identity():
    return {'schema':1,'version':VERSION,'input_sha256':INPUTS,
        'adapter_sha256':reference.sha(Path(__file__).read_bytes()),
        'headers_sha256':{name:reference.sha((DIRECTORY/name).read_bytes()) for name in HEADERS},
        'default_enabled':False,'implementation_level':'C numerical backend and finite control profile',
        'guest_software_modified':False,'source_role':'explicit MAIN linear16',
        'physical_ISP_equivalence':False,'complete_snapshot_supported':False}


def render(files):
    for name,expected in INPUTS.items():
        if reference.sha(files[name])!=expected: raise ValueError('CaptureWork requires frozen r69 '+name)
    result={name:data.decode('utf-8') for name,data in files.items()}; replace=reference.replace_once
    board=result['hw/arm/nikon-z72.c']
    board=replace(board,'#include "nikon-z62-paired-ingress-api.h"',
        '#include "nikon-z62-paired-ingress-api.h"\n#include "nikon-z62-capturework-api.h"')
    anchor='    boot_config_trace(s, address, (uint32_t)value, true);'
    board=replace(board,anchor,anchor+'\n    z62_capturework_control(s->paired_input,address,(uint32_t)value);')
    anchor='    boot_config->paired_input = input_config;'
    wiring='''
    if (z62) {
        const unsigned events[]={3,4,135};
        for (unsigned i=0;i<3;i++) qdev_connect_gpio_out_named(input_config,"capturework-complete",i,
            qdev_get_gpio_in_named(config,"input-event",events[i]));
    }'''
    board=replace(board,anchor,anchor+wiring)
    result['hw/arm/nikon-z72.c']=board
    source=result['hw/arm/nikon-z72-input-config.c']
    source=replace(source,'struct Z72InputConfig {','#include "nikon-z62-capturework-state.h"\n\nstruct Z72InputConfig {')
    source=replace(source,'    Z62SceneSource scene;','    Z62SceneSource scene;\n    Z62CaptureWork cw;')
    source=replace(source,'#include "nikon-z62-continuous-stats.h"',
        '#include "nikon-z62-continuous-stats.h"\n#include "nikon-z62-capturework-device.h"')
    source=replace(source,'    s->registers[offset / 4] = value;',
        '    s->registers[offset / 4] = value;\n    if (s->cw.enabled) s->cw.known[offset/4]=true;')
    source=replace(source,'    finite_reset(s);','    cw_reset(s);\n    finite_reset(s);')
    source=replace(source,'    scene_qom_init(obj);','    cw_init(obj);\n    scene_qom_init(obj);')
    source=replace(source,'    dc->realize = raw_realize;','    dc->realize = cw_realize;')
    source=replace(source,'    dc->unrealize = raw_unrealize;','    dc->unrealize = cw_unrealize;')
    source=replace(source,'    static const Property properties[] = {',
        '    static const Property properties[] = {\n        DEFINE_PROP_BOOL("z62-capturework", Z72InputConfig, cw.enabled, false),')
    source=replace(source,'    .instance_init = input_config_init,',
        '    .instance_init = input_config_init,\n    .instance_finalize = cw_finalize,')
    result['hw/arm/nikon-z72-input-config.c']=source
    raw=result['hw/arm/nikon-z62-functional-raw.h']
    raw=replace(raw,'    if (!s->functional_raw) {','    if (s->cw.enabled || !s->functional_raw) {')
    result['hw/arm/nikon-z62-functional-raw.h']=raw
    for name in HEADERS: result['hw/arm/'+name]=(DIRECTORY/name).read_text(encoding='utf-8')
    return {name:data.encode('utf-8') for name,data in result.items()}


def apply_source(source):
    source=Path(source)
    if not source.resolve().is_relative_to(WORK.resolve()): raise ValueError('Use independent CaptureWork workspace')
    result=render({name:(source/name).read_bytes() for name in INPUTS})
    for name,data in result.items(): (source/name).write_bytes(data)
    return result
