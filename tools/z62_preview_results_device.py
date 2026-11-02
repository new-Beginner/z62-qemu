"""Independent r47 results over the frozen r24 scene/preview source tree."""
from pathlib import Path
import reference_updates as reference

ROOT = Path(__file__).resolve().parents[1]
VERSION = '2026.11.02-r47'
WORK = ROOT/'.build'/('z62-preview-results-'+VERSION)
HEADERS = tuple(ROOT/'qemu/z62-preview-results'/n for n in
                ('nikon-z62-preview-results.h', 'nikon-z62-preview-results-profile.h'))
INPUTS = {'nikon-z72.c': 'b5fabad080fee2b23870aff65456f09f43c6f51cfc8aa0459858eb687ce926b8',
          'nikon-z62-preview.h': '60fcd24760314221b3f517db925a4b3516740e45c52dfe5d5346720a71b6d08c'}


def identity():
    return {'schema': 1, 'version': VERSION, 'input_sha256': INPUTS,
            'adapter_sha256': reference.sha(Path(__file__).read_bytes()),
            'headers_sha256': {p.name: reference.sha(p.read_bytes()) for p in HEADERS},
            'default_enabled': False, 'routing_level': 'B', 'pixel_processing_level': 'C',
            'profile': 'observed Z62 C1.70 three-output preview, all-or-reject',
            'result_bits': 0x61, 'statistics_bank0_completed': False,
            'software_callback_fields_used_for_success': False, 'guest_software_patched': False}


def render(files):
    for name, expected in INPUTS.items():
        if reference.sha(files[name]) != expected:
            raise ValueError('Preview results require unchanged r24 source: '+name)
    text = {n: data.decode('utf-8') for n, data in files.items()}
    replace = reference.replace_once
    board = text['nikon-z72.c']
    board = replace(board, '    bool z62_preview, preview_mapped, preview_source_valid, preview_flush_pending, preview_stopping;',
        '    bool z62_preview, preview_mapped, preview_source_valid, preview_flush_pending, preview_stopping;\n'
        '    bool z62_preview_results;\n'
        '    uint64_t preview_result_batches, preview_result_units, preview_result_rejected, preview_result_blocked;')
    board = replace(board, '    .version_id = 44,\n    .minimum_version_id = 44,',
                          '    .version_id = 45,\n    .minimum_version_id = 45,')
    board = replace(board, '        VMSTATE_UINT64(preview_flushes, NikonZ72BootConfig),',
        '        VMSTATE_UINT64(preview_flushes, NikonZ72BootConfig),\n'
        '        VMSTATE_BOOL(z62_preview_results, NikonZ72BootConfig),\n'
        '        VMSTATE_UINT64(preview_result_batches, NikonZ72BootConfig),\n'
        '        VMSTATE_UINT64(preview_result_units, NikonZ72BootConfig),\n'
        '        VMSTATE_UINT64(preview_result_rejected, NikonZ72BootConfig),\n'
        '        VMSTATE_UINT64(preview_result_blocked, NikonZ72BootConfig),')
    board = replace(board, '        DEFINE_PROP_BOOL("z62-preview", NikonZ72BootConfig, z62_preview, false),',
        '        DEFINE_PROP_BOOL("z62-preview", NikonZ72BootConfig, z62_preview, false),\n'
        '        DEFINE_PROP_BOOL("z62-preview-results", NikonZ72BootConfig, z62_preview_results, false),')
    preview = text['nikon-z62-preview.h']
    preview = replace(preview, 'static bool preview_ready(NikonZ72BootConfig *s)',
                      '#include "nikon-z62-preview-results.h"\n\nstatic bool preview_ready(NikonZ72BootConfig *s)')
    preview = replace(preview, '    /* Leave unacknowledged output intact, including masked completions. */',
        '    if (preview_results_pending(s)) {\n'
        '        s->preview_result_blocked++; s->preview_blocked++; return;\n'
        '    }\n    /* Leave unacknowledged output intact, including masked completions. */')
    preview = replace(preview, '    for(unsigned frame=0;frame<4;frame++) {\n        src[frame]=',
        '    if (!preview_results_prepare(s, w, h)) {\n'
        '        s->preview_result_rejected++; reason=10; goto rejected;\n'
        '    }\n    for(unsigned frame=0;frame<4;frame++) {\n        src[frame]=')
    preview = replace(preview, '    /* Only preview command bank1 completed. Bank0\'s statistics were not run. */',
        '    preview_results_finish(s);\n'
        '    /* Only preview command bank1 completed. Bank0\'s statistics were not run. */')
    preview = replace(preview, '    s->preview_source_valid=s->preview_flush_pending=s->preview_stopping=false;',
        '    preview_results_reset(s);\n    s->preview_source_valid=s->preview_flush_pending=s->preview_stopping=false;')
    preview = replace(preview, '    object_property_add_str(obj,"preview-reason",preview_reason_get,NULL);',
        '    object_property_add_str(obj,"preview-reason",preview_reason_get,NULL);\n    preview_results_qom_init(obj);')
    preview = replace(preview, '"success", "drain"};', '"success", "drain", "result-configuration"};')
    return {'nikon-z72.c': board, 'nikon-z62-preview.h': preview}


def apply_source(source):
    source = Path(source).resolve()
    if not source.is_relative_to(WORK.resolve()):
        raise ValueError('Preview results require their independent workspace')
    arm = source/'hw/arm'
    rendered = render({n: (arm/n).read_bytes() for n in INPUTS})
    for name, data in rendered.items():
        (arm/name).write_text(data, encoding='utf-8', newline='\n')
    for header in HEADERS:
        (arm/header.name).write_bytes(header.read_bytes())
    return identity()
