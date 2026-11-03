"""Independent r52 grid geometry and explicit retained-input job experiment."""
from pathlib import Path
import reference_updates as reference

ROOT = Path(__file__).resolve().parents[1]
VERSION = '2026.11.03-r52'
WORK = ROOT/'.build'/('z62-grid-geometry-'+VERSION)
PIXELS = ROOT/'qemu/z62-mode-geometry/nikon-z62-mode-grid-pixels.h'
INPUTS = {
    'nikon-z72.c': '7a4292cf8c25f134980269f0fdc342ec99e7a5b1732ab1ca60e24053a9b7983b',
    'nikon-z62-grid.h': '5c8196e7857ab5cf91bbfd75e094fe8c5aff990e823423bc69ee83db9a05eddf',
}


def identity():
    return {'schema': 1, 'version': VERSION, 'input_sha256': INPUTS,
            'adapter_sha256': reference.sha(Path(__file__).read_bytes()),
            'pixels_sha256': reference.sha(PIXELS.read_bytes()),
            'default_enabled': False, 'algorithm_level': 'C',
            'heights': [40, 34], 'width': 60,
            'retained_input_requires_separate_opt_in': True,
            'retained_input_is_new_acquisition': False,
            'physical_cache_lifetime_verified': False, 'guest_software_patched': False}


def render(files):
    for name, digest in INPUTS.items():
        if reference.sha(files[name]) != digest:
            raise ValueError('Grid geometry requires frozen r48 '+name)
    replace = reference.replace_once
    output = {name: value.decode('utf-8') for name, value in files.items()}
    board = output['nikon-z72.c']
    board = replace(board, '    bool z62_grid_process, grid_needs_check;',
                    '    bool z62_grid_process, grid_needs_check;\n'
                    '    bool z62_grid_geometry, z62_grid_retained_input;\n'
                    '    uint64_t grid_request_seq, grid_checked_request, grid_consumed_request;\n'
                    '    uint64_t grid_retained_jobs;')
    board = replace(board, '    .version_id = 46,\n    .minimum_version_id = 46,',
                    '    .version_id = 47,\n    .minimum_version_id = 47,')
    board = replace(board, '        VMSTATE_TIMER_PTR(grid_timer, NikonZ72BootConfig),',
                    '''        VMSTATE_TIMER_PTR(grid_timer, NikonZ72BootConfig),
        VMSTATE_BOOL(z62_grid_geometry, NikonZ72BootConfig),
        VMSTATE_BOOL(z62_grid_retained_input, NikonZ72BootConfig),
        VMSTATE_UINT64(grid_request_seq, NikonZ72BootConfig),
        VMSTATE_UINT64(grid_checked_request, NikonZ72BootConfig),
        VMSTATE_UINT64(grid_consumed_request, NikonZ72BootConfig),
        VMSTATE_UINT64(grid_retained_jobs, NikonZ72BootConfig),''')
    board = replace(board, '    if ((s->grid_supplied_mask & ~0x3fu)',
                    '''    if (s->grid_checked_request > s->grid_request_seq ||
        s->grid_consumed_request > s->grid_request_seq) { return -EINVAL; }
    if ((s->grid_supplied_mask & ~0x3fu)''')
    board = replace(board,
                    '        DEFINE_PROP_BOOL("z62-grid-process", NikonZ72BootConfig, z62_grid_process, false),',
                    '''        DEFINE_PROP_BOOL("z62-grid-process", NikonZ72BootConfig, z62_grid_process, false),
        DEFINE_PROP_BOOL("z62-grid-geometry", NikonZ72BootConfig, z62_grid_geometry, false),
        DEFINE_PROP_BOOL("z62-grid-retained-input", NikonZ72BootConfig, z62_grid_retained_input, false),''')
    output['nikon-z72.c'] = board
    grid = output['nikon-z62-grid.h']
    grid = replace(grid, '#include "nikon-z62-grid-pixels.h"',
                   '''#include "nikon-z62-grid-pixels.h"
#include "nikon-z62-mode-grid-pixels.h"

static unsigned z62_grid_rows(const NikonZ72BootConfig *s)
{
    return s->z62_grid_geometry && s->preview_core[0x2644/4] == 34 ? 34 : 40;
}''')
    grid = replace(grid, '    static const uint32_t ports[2][13] = {',
                   '    unsigned height = z62_grid_rows(s);\n'
                   '    static const uint32_t ports[2][13] = {')
    grid = replace(grid, 's->preview_core[0x2644/4] != 40',
                   's->preview_core[0x2644/4] != height')
    grid = replace(grid,
        '            if (i != 1 && s->preview_core[(0x440+p*0x40)/4+i] != ports[p][i]) { return false; }',
        '            uint32_t expected = i == 8 ? (height<<16)|60 : ports[p][i];\n'
        '            if (i != 1 && s->preview_core[(0x440+p*0x40)/4+i] != expected) { return false; }')
    grid = replace(grid, '        if (ldl_le_p(parameter+i*4) != body[i]) { return false; }',
                   '        uint32_t expected = i == 12 ? (height-1)<<16 : body[i];\n'
                   '        if (ldl_le_p(parameter+i*4) != expected) { return false; }')
    grid = replace(grid, '    uint64_t epoch[6];',
                   '    unsigned height = z62_grid_rows(s);\n'
                   '    size_t source_bytes = (size_t)128*height, destination_bytes = (size_t)96*height;\n'
                   '    uint64_t epoch[6];')
    grid = replace(grid, '    s->grid_checked_seq=s->grid_source_seq;\n    if (!z62_grid_profile(s))',
                   '    s->grid_checked_seq=s->grid_source_seq;\n'
                   '    s->grid_checked_request=s->grid_request_seq;\n    if (!z62_grid_profile(s))')
    grid = replace(grid, '    if (!fresh) { s->grid_reason=11; return; }',
                   '''    bool retained = !fresh && s->z62_grid_geometry &&
        s->z62_grid_retained_input && height == 34 &&
        s->grid_request_seq > s->grid_consumed_request;
    if (!fresh && !retained) { s->grid_reason=11; return; }''')
    grid = grid.replace('Z62_GRID_SRC_BYTES', 'source_bytes').replace('Z62_GRID_DST_BYTES', 'destination_bytes')
    grid = replace(grid, '''        if (!z62_grid_convert(input+(f*3)*source_bytes,
                              input+(f*3+1)*source_bytes,
                              input+(f*3+2)*source_bytes,source_bytes,
                              packed+f*destination_bytes,destination_bytes)) { goto rejected; }''',
                   '''        const uint8_t *planes[3] = {input+(f*3)*source_bytes,
            input+(f*3+1)*source_bytes, input+(f*3+2)*source_bytes};
        size_t available[3] = {source_bytes,source_bytes,source_bytes};
        size_t rows[3] = {128,128,128};
        if (!z62_mode_grid_convert(planes,available,60,height,rows,
                                  packed+f*destination_bytes,destination_bytes,96)) { goto rejected; }''')
    grid = replace(grid, '    s->grid_groups++; s->grid_reason=10;',
                   '    s->grid_groups++; s->grid_reason=10;\n'
                   '    s->grid_consumed_request=s->grid_request_seq;\n'
                   '    if (retained) { s->grid_retained_jobs++; }')
    grid = replace(grid,
                   '    if (!s->grid_needs_check && s->grid_source_seq == s->grid_checked_seq) { return; }',
                   '    if (!s->grid_needs_check && s->grid_source_seq == s->grid_checked_seq &&\n'
                   '        s->grid_request_seq == s->grid_checked_request) { return; }')
    grid = replace(grid, '    if (!z62_grid_supported(s)) { return; }\n    if ((offset==4',
                   '''    if (!z62_grid_supported(s)) { return; }
    /* An explicit new command is distinct from ACK and from a sensor frame.
     * Reuse of retained completed RGB is a separate C-level experiment. */
    if (s->z62_grid_geometry && s->z62_grid_retained_input &&
        s->preview_core[0x2644/4] == 34 && offset == 0x2648 && value == 3) {
        if (s->grid_request_seq == UINT64_MAX) {
            s->grid_reason=3; s->grid_rejected++; return;
        }
        s->grid_request_seq++;
        s->grid_needs_check=true;
    }
    if ((offset==4''')
    grid = replace(grid, '        s->grid_needs_check=false; s->grid_reason=2;',
                   '        s->grid_needs_check=false; s->grid_reason=2;\n'
                   '        s->grid_checked_request=s->grid_consumed_request=s->grid_request_seq;')
    grid = replace(grid, '    s->grid_reason=0;',
                   '    s->grid_reason=0;\n'
                   '    s->grid_request_seq=s->grid_checked_request=s->grid_consumed_request=0;\n'
                   '    s->grid_retained_jobs=0;')
    grid = replace(grid, '    object_property_add_str(obj,"grid-reason",z62_grid_reason,NULL);',
                   '''    object_property_add_str(obj,"grid-reason",z62_grid_reason,NULL);
    object_property_add_uint64_ptr(obj,"grid-config-requests",&s->grid_request_seq,OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(obj,"grid-config-consumed",&s->grid_consumed_request,OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(obj,"grid-retained-jobs",&s->grid_retained_jobs,OBJ_PROP_FLAG_READ);''')
    output['nikon-z62-grid.h'] = grid
    output[PIXELS.name] = PIXELS.read_text(encoding='utf-8')
    return {name: value.encode('utf-8') for name, value in output.items()}


def apply_source(source):
    root = Path(source)/'hw/arm'
    prepared = render({name: (root/name).read_bytes() for name in INPUTS})
    for name, value in prepared.items():
        (root/name).write_bytes(value)
    return prepared
