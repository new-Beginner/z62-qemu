"""r91 opt-in C MAIN policy for the original observed shared9530 word.

Keep r89 files immutable. Zero remains the legacy finite recipe; 0x200040 is
accepted only with the explicit external-MAIN policy, and remains visible in
the committed output metadata. Other nonzero physical selections still reject.
"""
from pathlib import Path
import reference_updates as reference
import z62_capturework_device as parent

ROOT=Path(__file__).resolve().parents[1]
VERSION='2026.11.04-r91'
WORK=ROOT/'.build'/('z62-capturework-policy-'+VERSION)
INPUTS={
    'hw/arm/nikon-z62-capturework-device.h':'7a2f7b70c16cd83e925d511c5ba11ecf8855d9be5409ba288b279a0780fdba18',
    'hw/arm/nikon-z62-capturework-state.h':'44a368a5dee9079de666b0d632ecc168d63a5508cb2f26ee0fbdfa461ed05b51',
    'hw/arm/nikon-z72-input-config.c':'8ae1182132e156b6168b3247e68974b749f63414f4dffe669f0fb083bdd98689',
}


def identity():
    return {'schema':1,'version':VERSION,'input_sha256':INPUTS,
        'adapter_sha256':reference.sha(Path(__file__).read_bytes()),'parent_capturework':parent.identity(),
        'property':'z62-capturework-policy0','default_enabled':False,
        'supported_shared_source_words':[0,0x200040],'source_role':'explicit C MAIN linear16',
        'physical_source_pair_implemented':False,'pixel_arithmetic_changed':False,
        'physical_ISP_equivalence':False,'guest_software_modified':False}


def render(files):
    for name,expected in INPUTS.items():
        if reference.sha(files[name])!=expected: raise ValueError('Policy layer requires frozen r89 '+name)
    result={name:data.decode('utf-8') for name,data in files.items()}; replace=reference.replace_once
    state=result['hw/arm/nikon-z62-capturework-state.h']
    state=replace(state,'    bool enabled, stopping, valid[3], known[0x4000/4];',
        '    bool enabled, stopping, external_policy0, valid[3], known[0x4000/4];\n    uint32_t output_shared_source_word;')
    result['hw/arm/nikon-z62-capturework-state.h']=state
    header=result['hw/arm/nikon-z62-capturework-device.h']
    header=replace(header,'p[3] || p[4] || p[5] || p[6]!=2 || p[7] ||',
        'p[3] || p[4] || p[5] || p[6]!=2 ||\n'
        '        (p[7] && (!s->cw.external_policy0 || p[7]!=0x200040)) ||')
    header=replace(header,'    c->output_meta=task->lease.meta; c->output_transfer=task->transfer; c->output_valid=true;',
        '    c->output_shared_source_word=task->profile.packing[7];\n'
        '    c->output_meta=task->lease.meta; c->output_transfer=task->transfer; c->output_valid=true;')
    header=replace(header,'    GString *out=g_string_new(NULL);',
        '    GString *out=g_string_new(NULL);\n'
        '    g_string_append_printf(out,"{\\\"external_main_policy0\\\":%s,\\\"configured_shared_source_word\\\":%u,\\\"output_shared_source_word\\\":%u,",\n'
        '        c->external_policy0?"true":"false",c->profile.packing[7],c->output_shared_source_word);')
    header=replace(header,'g_string_append_printf(out,"{\\\"enabled\\\":%s,',
        'g_string_append_printf(out,"\\\"enabled\\\":%s,')
    header=replace(header,'    if (!s->cw.enabled) return;',
        '    if (s->cw.external_policy0 && !s->cw.enabled) {\n'
        '        error_setg(errp,"External MAIN policy0 requires CaptureWork"); return;\n'
        '    }\n    if (!s->cw.enabled) return;')
    result['hw/arm/nikon-z62-capturework-device.h']=header
    source=result['hw/arm/nikon-z72-input-config.c']
    anchor='        DEFINE_PROP_BOOL("z62-capturework", Z72InputConfig, cw.enabled, false),'
    source=replace(source,anchor,anchor+'\n        DEFINE_PROP_BOOL("z62-capturework-policy0", Z72InputConfig, cw.external_policy0, false),')
    result['hw/arm/nikon-z72-input-config.c']=source
    return {name:data.encode('utf-8') for name,data in result.items()}
