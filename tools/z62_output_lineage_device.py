"""Default-off provenance observer over frozen r66; no pixel/control changes."""
from pathlib import Path
import reference_updates as reference

ROOT=Path(__file__).resolve().parents[1]
VERSION='2026.11.03-r69'
WORK=ROOT/'.build'/('z62-output-lineage-'+VERSION)
HEADER=ROOT/'qemu/z62-output-lineage/nikon-z62-output-lineage.h'
INPUTS={
    'hw/arm/nikon-z72.c':'8df32293617e1164037b4ca89e86e8ff398388ff228e8230d3c7f74004a250d2',
    'hw/arm/nikon-z72-input-config.c':'f8a66caed246e404e65c0cb1dc64505d228aa8bc7d77000e0d24be87fca08ca5',
    'hw/arm/nikon-z62-preview.h':'08689e6ea7ebdbe4335bf56a4345389b192cb111ec0f24cd86f7aaa4349366bb',
    'hw/arm/nikon-z62-video-isp.h':'a805f05cb75cba777c06237a381d59eb0c4def821da122c361812f84143648ec',
    'hw/arm/nikon-z62-paired-ingress.h':'cf58633af355c6176fbb22d94b389bdbe3d50c480e4d1c7e899b2093f16420b9',
    'hw/arm/nikon-z62-paired-ingress-api.h':'791f58ac71bb9c26c5ccbf115f6843f00daabe97eb5e261469d79d25910b66bd',
}


def identity():
    return {'schema':1,'version':VERSION,'input_sha256':INPUTS,
        'adapter_sha256':reference.sha(Path(__file__).read_bytes()),'header_sha256':reference.sha(HEADER.read_bytes()),
        'default_enabled':False,'readonly_property':'paired-output-lineage','vmstate_version':55,
        'pixel_arithmetic_changed':False,'control_or_irq_changed':False,'guest_software_patched':False,
        'physical_provenance_protocol':False,'scope':'device-input-to-software-isp-output'}


def render(files):
    for name,digest in INPUTS.items():
        if reference.sha(files[name])!=digest:
            raise ValueError('Output lineage requires frozen r66 '+name)
    result={name:data.decode('utf-8') for name,data in files.items()}
    replace=reference.replace_once
    board=result['hw/arm/nikon-z72.c']
    anchor='    uint64_t paired_ingress_retired_notifications;'
    fields='''
    bool z62_output_lineage, lineage_source_valid, lineage_video_valid, lineage_output_valid;
    uint64_t lineage_source_seq, lineage_video_seq, lineage_output_seq, lineage_output_count;
    uint64_t lineage_source_tags[4], lineage_video_tags[4], lineage_output_tags[4];
    uint32_t lineage_source_kind, lineage_video_kind, lineage_output_kind, lineage_output_mode;'''
    board=replace(board,anchor,anchor+fields)
    board=replace(board,'    .version_id = 54,\n    .minimum_version_id = 54,',
                  '    .version_id = 55,\n    .minimum_version_id = 55,')
    anchor='        VMSTATE_UINT64(paired_ingress_retired_notifications, NikonZ72BootConfig),'
    serialized='\n'
    for name in ('z62_output_lineage','lineage_source_valid','lineage_video_valid','lineage_output_valid'):
        serialized+='        VMSTATE_BOOL('+name+', NikonZ72BootConfig),\n'
    for name in ('lineage_source_seq','lineage_video_seq','lineage_output_seq','lineage_output_count'):
        serialized+='        VMSTATE_UINT64('+name+', NikonZ72BootConfig),\n'
    for name in ('lineage_source_tags','lineage_video_tags','lineage_output_tags'):
        serialized+='        VMSTATE_UINT64_ARRAY('+name+', NikonZ72BootConfig, 4),\n'
    for name in ('lineage_source_kind','lineage_video_kind','lineage_output_kind','lineage_output_mode'):
        serialized+='        VMSTATE_UINT32('+name+', NikonZ72BootConfig),\n'
    board=replace(board,anchor,anchor+serialized.rstrip())
    anchor='    if (video_post_load(s)) { return -EINVAL; }'
    board=replace(board,anchor,anchor+'\n    if (output_lineage_post_load(s)) { return -EINVAL; }')
    anchor='        DEFINE_PROP_BOOL("z62-paired-ingress", NikonZ72BootConfig, z62_paired_ingress, false),'
    board=replace(board,anchor,anchor+'\n        DEFINE_PROP_BOOL("z62-output-lineage", NikonZ72BootConfig, z62_output_lineage, false),')
    anchor='    preview_realize(s, root);'
    board=replace(board,anchor,'''    if (s->z62_output_lineage && (!s->z62_paired_ingress || !s->z62_preview_results)) {
        error_setg(errp,"z62-output-lineage needs the explicit paired input and preview results profile");
        return;
    }
'''+anchor)
    result['hw/arm/nikon-z72.c']=board
    api=result['hw/arm/nikon-z62-paired-ingress-api.h']
    api=replace(api,'#endif','bool z62_paired_scene_last_used(DeviceState *dev, uint64_t tags[4]);\n#endif')
    result['hw/arm/nikon-z62-paired-ingress-api.h']=api
    source=result['hw/arm/nikon-z72-input-config.c']
    source=replace(source,'#include "nikon-z62-functional-raw.h"','''bool z62_paired_scene_last_used(DeviceState *dev, uint64_t tags[4])
{
    Z72InputConfig *s=Z72_INPUT_CONFIG(dev);
    if (!s->z62_layout || !s->scene.enabled || !s->scene.uses || !s->scene.used_publish_id) return false;
    tags[0]=s->scene.used_epoch; tags[1]=s->scene.used_publish_id;
    tags[2]=s->scene.used_frame_id; tags[3]=s->scene.used_time_ns;
    return true;
}

#include "nikon-z62-functional-raw.h"''')
    result['hw/arm/nikon-z72-input-config.c']=source
    preview=result['hw/arm/nikon-z62-preview.h']
    preview=replace(preview,'#include "nikon-z62-video-isp.h"',
                    '#include "nikon-z62-output-lineage.h"\n#include "nikon-z62-video-isp.h"')
    preview=replace(preview,'    s->preview_source_valid=true;\n    video_source_notify(s);',
                    '    s->preview_source_valid=true;\n    output_lineage_raw_source(s);\n    video_source_notify(s);')
    preview=replace(preview,'    s->preview_reason=8;\n    preview_results_finish(s);',
                    '    s->preview_reason=8;\n    output_lineage_commit_photo(s);\n    preview_results_finish(s);')
    preview=replace(preview,'static void preview_reset(NikonZ72BootConfig *s)\n{',
                    'static void preview_reset(NikonZ72BootConfig *s)\n{\n    output_lineage_reset(s);')
    preview=replace(preview,'static void preview_init(Object *obj)\n{',
                    'static void preview_init(Object *obj)\n{\n    output_lineage_init(obj);')
    result['hw/arm/nikon-z62-preview.h']=preview
    video=result['hw/arm/nikon-z62-video-isp.h']
    video=replace(video,'static void video_drop_source(NikonZ72BootConfig *s)\n{',
                  'static void video_drop_source(NikonZ72BootConfig *s)\n{\n    output_lineage_video_drop(s);')
    video=replace(video,'    s->video_source_valid=true;s->video_captures++;',
                  '    s->video_source_valid=true;s->video_captures++;\n    output_lineage_video_capture(s);')
    video=replace(video,'    video_drop_source(s);\n    stl_le_p(s->transfer_table+0x20,',
                  '    output_lineage_commit_video(s);\n    video_drop_source(s);\n    stl_le_p(s->transfer_table+0x20,')
    result['hw/arm/nikon-z62-video-isp.h']=video
    paired=result['hw/arm/nikon-z62-paired-ingress.h']
    paired=replace(paired,'    s->preview_source_seq=sequence+1; s->preview_source_valid=true;',
                    '    s->preview_source_seq=sequence+1; s->preview_source_valid=true;\n    output_lineage_source(s,tags,2);')
    result['hw/arm/nikon-z62-paired-ingress.h']=paired
    result['hw/arm/'+HEADER.name]=HEADER.read_text(encoding='utf-8')
    return {name:data.encode('utf-8') for name,data in result.items()}


def apply_source(source):
    source=Path(source)
    if not source.resolve().is_relative_to(WORK.resolve()):
        raise ValueError('Output lineage needs its independent workspace')
    result=render({name:(source/name).read_bytes() for name in INPUTS})
    for name,data in result.items():
        (source/name).write_bytes(data)
    return result
