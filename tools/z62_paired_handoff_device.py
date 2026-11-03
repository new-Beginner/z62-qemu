"""r66 retires an unowned old notification only after successful new input DMA."""
from pathlib import Path
import reference_updates as reference

ROOT=Path(__file__).resolve().parents[1]
VERSION='2026.11.03-r66'
WORK=ROOT/'.build'/('z62-paired-handoff-'+VERSION)
INPUTS={
    'hw/arm/nikon-z72.c':'90959912b67d4411dca068b2259b66a2e37d02242d27b8a45b2b34452bc72d96',
    'hw/arm/nikon-z62-paired-ingress.h':'fdd0a1c7c7cf89ef4287cca465574ede8b0e11f8ff48f71540d19b33614c8028',
}
HEADERS={}


def identity():
    return {'schema':1,'version':VERSION,'input_sha256':INPUTS,
        'adapter_sha256':reference.sha(Path(__file__).read_bytes()),'implementation_level':'C',
        'default_enabled':False,'new_completion_emitted':False,'owned_pending_source_preserved':True,
        'scheduled_old_work_preserved':True,'retirement_counted_after_successful_dma':True,
        'guest_software_patched':False,'physical_protocol_equivalent':False,'vmstate_version':54}


def render(files):
    for name,digest in INPUTS.items():
        if reference.sha(files[name])!=digest:
            raise ValueError('Paired handoff correction requires frozen r65 '+name)
    result={name:data.decode('utf-8') for name,data in files.items()}
    replace=reference.replace_once
    board=result['hw/arm/nikon-z72.c']
    board=replace(board,'    uint64_t paired_ingress_tags[4];',
                  '    uint64_t paired_ingress_tags[4];\n    uint64_t paired_ingress_retired_notifications;')
    board=replace(board,'    .version_id = 53,\n    .minimum_version_id = 53,',
                  '    .version_id = 54,\n    .minimum_version_id = 54,')
    anchor='        VMSTATE_UINT64_ARRAY(paired_ingress_tags, NikonZ72BootConfig, 4),'
    board=replace(board,anchor,anchor+'\n        VMSTATE_UINT64(paired_ingress_retired_notifications, NikonZ72BootConfig),')
    board=replace(board,'    if (s->paired_ingress_reason > PAIRED_SEQUENCE ||',
                  '    if (s->paired_ingress_retired_notifications > s->paired_ingress_frames ||\n        s->paired_ingress_reason > PAIRED_SEQUENCE ||')
    result['hw/arm/nikon-z72.c']=board
    source=result['hw/arm/nikon-z62-paired-ingress.h']
    source=replace(source,'        (s->preview_source_valid && s->preview_source_seq>s->preview_last_seq)) {',
                   '''        (s->preview_source_valid && s->preview_source_seq>s->preview_last_seq &&
         (s->paired_ingress_owns_source || timer_pending(s->preview_timer)))) {''')
    anchor='    uint64_t sequence=MAX(s->preview_source_seq,s->preview_last_seq), tags[4];'
    source=replace(source,anchor,'''    /* An unscheduled old RAW notification is not an owned paired cohort.
     * Actual pending output and scheduled work remain protected above. Do
     * not discard it or signal completion before new pixel DMA succeeds. */
    bool retire_old=s->preview_source_valid && s->preview_source_seq>s->preview_last_seq &&
                    !s->paired_ingress_owns_source;
'''+anchor)
    anchor='    memcpy(s->preview_source,source,sizeof(source));'
    source=replace(source,anchor,'    if (retire_old) s->paired_ingress_retired_notifications++;\n'+anchor)
    anchor='    memset(s->paired_ingress_tags,0,sizeof(s->paired_ingress_tags));'
    source=replace(source,anchor,'    s->paired_ingress_retired_notifications=0;\n'+anchor)
    anchor='    object_property_add_uint64_ptr(obj,"paired-ingress-frames",&s->paired_ingress_frames,OBJ_PROP_FLAG_READ);'
    source=replace(source,anchor,anchor+'\n    object_property_add_uint64_ptr(obj,"paired-ingress-retired-notifications",&s->paired_ingress_retired_notifications,OBJ_PROP_FLAG_READ);')
    result['hw/arm/nikon-z62-paired-ingress.h']=source
    return {name:data.encode('utf-8') for name,data in result.items()}


def apply_source(source):
    root=Path(source)
    if not root.resolve().is_relative_to(WORK.resolve()):
        raise ValueError('Paired handoff must use an independent workspace')
    result=render({name:(root/name).read_bytes() for name in INPUTS})
    for name,data in result.items():
        (root/name).write_bytes(data)
    return result
