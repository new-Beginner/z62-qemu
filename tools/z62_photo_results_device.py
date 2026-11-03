"""r53 captured photo-return output recipe and opt-in re-entry work."""
from pathlib import Path
import reference_updates as reference

ROOT=Path(__file__).resolve().parents[1]
VERSION='2026.11.03-r53'
WORK=ROOT/'.build'/('z62-photo-results-'+VERSION)
HEADER=ROOT/'qemu/z62-photo-results/nikon-z62-photo-results-profile.h'
INPUTS={
    'nikon-z72.c':'7bdca0c869400ed0b65cd8e9f30c9fd9d2cd0472bf1e1a061dea9d63022a6996',
    'nikon-z62-preview-results.h':'05cbf2262eaad881ecee9a7ada3874f0d9dc099ba625e7089da0bc54395abf6b',
    'nikon-z62-grid.h':'23bd1ddf9713ddd9660442b02f2a8f40c28da956abd5b7266f8ab7d57468a8ad',
}


def identity():
    return {'schema':1,'version':VERSION,'input_sha256':INPUTS,
            'adapter_sha256':reference.sha(Path(__file__).read_bytes()),
            'profile_sha256':reference.sha(HEADER.read_bytes()),'default_enabled':False,
            'new_active_geometry':[1024,680],'new_internal_rows':698,
            'physical_cache_lifetime_verified':False,'guest_software_patched':False,
            'cached_photo_reentry_requires_both_opt_ins':True}


def render(files):
    for name,digest in INPUTS.items():
        if reference.sha(files[name])!=digest:
            raise ValueError('Photo output layout requires frozen r52 '+name)
    replace=reference.replace_once
    output={name:data.decode('utf-8') for name,data in files.items()}
    board=output['nikon-z72.c']
    board=replace(board,'    uint64_t grid_retained_jobs;',
                  '    uint64_t grid_retained_jobs;\n'
                  '    uint32_t grid_completed_rows;\n'
                  '    bool z62_photo_result_layouts;')
    board=replace(board,'    .version_id = 47,\n    .minimum_version_id = 47,',
                  '    .version_id = 48,\n    .minimum_version_id = 48,')
    board=replace(board,'        VMSTATE_UINT64(grid_retained_jobs, NikonZ72BootConfig),',
                  '        VMSTATE_UINT64(grid_retained_jobs, NikonZ72BootConfig),\n'
                  '        VMSTATE_UINT32(grid_completed_rows, NikonZ72BootConfig),\n'
                  '        VMSTATE_BOOL(z62_photo_result_layouts, NikonZ72BootConfig),')
    board=replace(board,'    if (s->grid_checked_request > s->grid_request_seq ||',
                  '    if (s->grid_completed_rows && s->grid_completed_rows != 34 &&\n'
                  '        s->grid_completed_rows != 40) { return -EINVAL; }\n'
                  '    if (s->grid_checked_request > s->grid_request_seq ||')
    board=replace(board,
                  '        DEFINE_PROP_BOOL("z62-grid-geometry", NikonZ72BootConfig, z62_grid_geometry, false),',
                  '        DEFINE_PROP_BOOL("z62-grid-geometry", NikonZ72BootConfig, z62_grid_geometry, false),\n'
                  '        DEFINE_PROP_BOOL("z62-photo-result-layouts", NikonZ72BootConfig, z62_photo_result_layouts, false),')
    output['nikon-z72.c']=board
    result=output['nikon-z62-preview-results.h']
    result=replace(result,'#include "nikon-z62-preview-results-profile.h"',
                   '#include "nikon-z62-preview-results-profile.h"\n'
                   '#include "nikon-z62-photo-results-profile.h"')
    result=replace(result,
                   '        mask |= z62_preview_result_mask(i, widths[i], heights[i], registers, parameters);',
                   '''        uint32_t bit = z62_preview_result_mask(i, widths[i], heights[i], registers, parameters);
        if (!bit && s->z62_photo_result_layouts) {
            bit = z62_photo_result_mask(i, widths[i], heights[i], registers, parameters);
        }
        mask |= bit;''')
    output['nikon-z62-preview-results.h']=result
    grid=output['nikon-z62-grid.h']
    grid=replace(grid,'s->z62_grid_retained_input && height == 34 &&',
                 '''s->z62_grid_retained_input && (height == 34 ||
        (s->z62_photo_result_layouts && height == 40 && s->grid_completed_rows == 34)) &&''')
    grid=replace(grid,'        s->preview_core[0x2644/4] == 34 && offset == 0x2648 && value == 3) {',
                 '''        (s->preview_core[0x2644/4] == 34 ||
         (s->z62_photo_result_layouts && s->preview_core[0x2644/4] == 40 &&
          s->grid_completed_rows == 34)) && offset == 0x2648 && value == 3) {''')
    grid=replace(grid,'    if (retained) { s->grid_retained_jobs++; }',
                 '    if (retained) { s->grid_retained_jobs++; }\n'
                 '    s->grid_completed_rows=height;')
    grid=replace(grid,'    s->grid_retained_jobs=0;',
                 '    s->grid_retained_jobs=0;\n    s->grid_completed_rows=0;')
    grid=replace(grid,'    object_property_add_uint64_ptr(obj,"grid-retained-jobs",&s->grid_retained_jobs,OBJ_PROP_FLAG_READ);',
                 '    object_property_add_uint64_ptr(obj,"grid-retained-jobs",&s->grid_retained_jobs,OBJ_PROP_FLAG_READ);\n'
                 '    object_property_add_uint32_ptr(obj,"grid-last-rows",&s->grid_completed_rows,OBJ_PROP_FLAG_READ);')
    output['nikon-z62-grid.h']=grid
    output[HEADER.name]=HEADER.read_text(encoding='utf-8')
    return {name:data.encode('utf-8') for name,data in output.items()}


def apply_source(source):
    root=Path(source)/'hw/arm'
    result=render({name:(root/name).read_bytes() for name in INPUTS})
    for name,data in result.items(): (root/name).write_bytes(data)
    return result
