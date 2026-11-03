"""Frozen r53 -> independent default-off C video transaction, r59."""
from pathlib import Path
import reference_updates as reference

ROOT=Path(__file__).resolve().parents[1]
VERSION='2026.11.03-r59'
WORK=ROOT/'.build'/('z62-video-isp-'+VERSION)
INPUTS={
    'nikon-z72.c':'45d9eb99f9487a3f6f80082c0208d27d078cb01b288680f3c0dfd15a42fa050b',
    'nikon-z62-preview.h':'50d4bc970205bf2e61fb5d740c72f1878fd1902907e799ab1060495bf0b4d553',
    'nikon-z62-preview-results.h':'5999148040cb34617c1f4e194d71251db5f05477528a01a9bde8be1523bd152a'}
HEADERS={name:ROOT/'qemu/z62-video-isp'/name for name in
         ('nikon-z62-video-pixels.h','nikon-z62-video-profile.h','nikon-z62-video-isp.h')}
HEADERS['nikon-z62-video-source-pixels.h']=ROOT/'qemu/z62-video-source/nikon-z62-video-source-pixels.h'


def identity():
    return {'schema':1,'version':VERSION,'input_sha256':INPUTS,
            'adapter_sha256':reference.sha(Path(__file__).read_bytes()),
            'headers_sha256':{name:reference.sha(path.read_bytes()) for name,path in HEADERS.items()},
            'default_enabled':False,'explicit_even_origin_required':True,
            'software_view':[1516,854,2288],'main':[1508,846,1520],'work':[754,423,1520],
            'work_is_temporal_history':False,'physical_isp_equivalent':False,
            'owned_identical_raw_cohort_required':True,'vmstate_version':49,'guest_software_patched':False}


def render(files):
    for name,digest in INPUTS.items():
        if reference.sha(files[name])!=digest: raise ValueError('Video ISP requires frozen r53 '+name)
    replace=reference.replace_once
    result={name:data.decode('utf-8') for name,data in files.items()}
    board=result['nikon-z72.c']
    board=replace(board,'#include "nikon-z62-preview-pixels.h"',
                  '#include "nikon-z62-preview-pixels.h"\n#include "nikon-z62-video-pixels.h"')
    board=replace(board,'    Z62PreviewPixels *preview_pixels;', '''    Z62PreviewPixels *preview_pixels;
    bool z62_video_isp, video_source_valid;
    int32_t video_origin_x, video_origin_y;
    uint32_t video_reason, video_source_bytes, video_source_address[4];
    uint64_t video_source_seq, video_captures, video_coalesced, video_source_rejected, video_source_cancelled;
    uint64_t video_batches, video_main_bytes, video_work_bytes, video_rejected, video_blocked;
    uint8_t video_source_data[4u*Z62_VIDEO_INPUT_BYTES];
    Z62VideoPixels *video_pixels;''')
    board=replace(board,'    .version_id = 48,\n    .minimum_version_id = 48,',
                  '    .version_id = 49,\n    .minimum_version_id = 49,\n    .pre_load = video_pre_load,')
    board=replace(board,'    if (s->grid_completed_rows &&',
                  '    if (video_post_load(s)) { return -EINVAL; }\n    if (s->grid_completed_rows &&')
    fields='''        VMSTATE_BOOL(z62_video_isp, NikonZ72BootConfig),
        VMSTATE_BOOL(video_source_valid, NikonZ72BootConfig),
        VMSTATE_INT32(video_origin_x, NikonZ72BootConfig),
        VMSTATE_INT32(video_origin_y, NikonZ72BootConfig),
        VMSTATE_UINT32(video_reason, NikonZ72BootConfig),
        VMSTATE_UINT32(video_source_bytes, NikonZ72BootConfig),
        VMSTATE_UINT32_ARRAY(video_source_address, NikonZ72BootConfig, 4),
        VMSTATE_UINT64(video_source_seq, NikonZ72BootConfig),
        VMSTATE_UINT64(video_captures, NikonZ72BootConfig),
        VMSTATE_UINT64(video_coalesced, NikonZ72BootConfig),
        VMSTATE_UINT64(video_source_rejected, NikonZ72BootConfig),
        VMSTATE_UINT64(video_source_cancelled, NikonZ72BootConfig),
        VMSTATE_UINT64(video_batches, NikonZ72BootConfig),
        VMSTATE_UINT64(video_main_bytes, NikonZ72BootConfig),
        VMSTATE_UINT64(video_work_bytes, NikonZ72BootConfig),
        VMSTATE_UINT64(video_rejected, NikonZ72BootConfig),
        VMSTATE_UINT64(video_blocked, NikonZ72BootConfig),
        VMSTATE_BUFFER(video_source_data, NikonZ72BootConfig),'''
    board=replace(board,'        VMSTATE_BOOL(z62_photo_result_layouts, NikonZ72BootConfig),',
                  '        VMSTATE_BOOL(z62_photo_result_layouts, NikonZ72BootConfig),\n'+fields)
    board=replace(board,'    preview_realize(s, root);',
                  '    if (!video_configuration(s, errp)) { return; }\n    preview_realize(s, root);')
    prop='        DEFINE_PROP_BOOL("z62-photo-result-layouts", NikonZ72BootConfig, z62_photo_result_layouts, false),'
    board=replace(board,prop,prop+'\n'+'''        DEFINE_PROP_BOOL("z62-video-isp", NikonZ72BootConfig, z62_video_isp, false),
        DEFINE_PROP_INT32("z62-video-origin-x", NikonZ72BootConfig, video_origin_x, INT32_MIN),
        DEFINE_PROP_INT32("z62-video-origin-y", NikonZ72BootConfig, video_origin_y, INT32_MIN),''')
    result['nikon-z72.c']=board
    preview=result['nikon-z62-preview.h']
    preview=replace(preview,'#include "nikon-z62-grid.h"',
                    '#include "nikon-z62-grid.h"\n#include "nikon-z62-video-isp.h"')
    preview=replace(preview,'    s->preview_source_valid=true;\n    preview_schedule(s);',
                    '    s->preview_source_valid=true;\n    video_source_notify(s);\n    preview_schedule(s);')
    preview=replace(preview,'    s->preview_attempts++;', '''    s->preview_attempts++;
    if (s->z62_video_isp && (s->preview_raw[0x48/4]==0x05ec0356 ||
                            s->preview_core[0x2600/4]==0x300)) {
        video_tick(s); return;
    }''')
    preview=replace(preview,'static void preview_cancel(NikonZ72BootConfig *s)\n{',
                    'static void preview_cancel(NikonZ72BootConfig *s)\n{\n    video_cancel(s);')
    preview=replace(preview,'if(offset==8 && value==1 && s->preview_raw[0x48/4]==0x05ea03ee)',
                    'if(offset==8 && value==1 && (s->preview_raw[0x48/4]==0x05ea03ee ||\n'
                    '           (s->z62_video_isp && s->preview_raw[0x48/4]==0x05ec0356)))')
    preview=replace(preview,'static void preview_reset(NikonZ72BootConfig *s)\n{',
                    'static void preview_reset(NikonZ72BootConfig *s)\n{\n    video_reset(s);')
    preview=replace(preview,'    preview_results_qom_init(obj);',
                    '    preview_results_qom_init(obj);\n    video_qom_init(obj);')
    preview=replace(preview,'static void preview_finalize(NikonZ72BootConfig *s)\n{',
                    'static void preview_finalize(NikonZ72BootConfig *s)\n{\n    video_cancel(s);')
    result['nikon-z62-preview.h']=preview
    results=result['nikon-z62-preview-results.h']
    results=replace(results,'#include "nikon-z62-photo-results-profile.h"',
                    '#include "nikon-z62-photo-results-profile.h"\n#include "nikon-z62-video-profile.h"')
    results=replace(results,'        mask |= bit;',
                    '        if (!bit && s->z62_video_isp) { bit=z62_video_result_mask(i,widths[i],heights[i],registers,parameters); }\n'
                    '        mask |= bit;')
    result['nikon-z62-preview-results.h']=results
    for name,path in HEADERS.items(): result[name]=path.read_text(encoding='utf-8')
    return {name:data.encode('utf-8') for name,data in result.items()}


def apply_source(source):
    root=Path(source)/'hw/arm'
    output=render({name:(root/name).read_bytes() for name in INPUTS})
    for name,data in output.items(): (root/name).write_bytes(data)
    return output
