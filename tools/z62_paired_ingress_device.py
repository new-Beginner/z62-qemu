"""Independent, default-off level-C paired input; frozen ancestors stay intact."""
from pathlib import Path
import reference_updates as reference

ROOT = Path(__file__).resolve().parents[1]
VERSION = '2026.11.03-r65'
WORK = ROOT/'.build'/('z62-paired-ingress-'+VERSION)
INPUTS = {
    'hw/arm/nikon-z72.c': '8988e744f4eeefea1a2e5ff008461351643dcac988ac7a65729890ef65aba00f',
    'hw/arm/nikon-z72-input-config.c': 'bdad9683c5c60bcd4b036922d9fd749a8188501a4ac286dd7336b9c94c99e914',
    'hw/arm/nikon-z62-preview.h': '2405ef9f992b7e19fcf99d4c97c167a1eeefd227afdebc4f8e85e78928681f12',
}
HEADERS = {name: ROOT/'qemu/z62-paired-ingress'/name for name in
           ('nikon-z62-paired-ingress-api.h', 'nikon-z62-paired-ingress.h')}


def identity():
    return {'schema': 1, 'version': VERSION, 'input_sha256': INPUTS,
            'adapter_sha256': reference.sha(Path(__file__).read_bytes()),
            'headers_sha256': {n: reference.sha(p.read_bytes()) for n, p in HEADERS.items()},
            'implementation_level': 'C', 'default_enabled': False,
            'requires_existing_scene': True, 'requires_legacy_raw_stopped': True,
            'writes_raw_start_latch': False, 'source_emits_irq': False,
            'statistics_generated': False, 'physical_protocol_equivalent': False,
            'guest_software_patched': False, 'period_ns_assumption': 33333333, 'vmstate_version': 53}


def render(files):
    for name, digest in INPUTS.items():
        if reference.sha(files[name]) != digest:
            raise ValueError('Paired software input requires frozen r64b '+name)
    result = {name: data.decode('utf-8') for name, data in files.items()}
    replace = reference.replace_once
    board = replace(result['hw/arm/nikon-z72.c'], '#include "nikon-z62-video-pixels.h"',
                    '#include "nikon-z62-video-pixels.h"\n#include "nikon-z62-paired-ingress-api.h"')
    board = replace(board, '    bool z62_raw_stop_control;', '''    bool z62_raw_stop_control;
    bool z62_paired_ingress, paired_ingress_active, paired_ingress_owns_source;
    uint32_t paired_ingress_reason;
    uint64_t paired_ingress_attempts, paired_ingress_frames, paired_ingress_bytes;
    uint64_t paired_ingress_rejected, paired_ingress_blocked, paired_ingress_dma_ns;
    uint64_t paired_ingress_tags[4];
    QEMUTimer *paired_ingress_timer;
    DeviceState *paired_input;''')
    board = replace(board, '    .version_id = 52,\n    .minimum_version_id = 52,',
                    '    .version_id = 53,\n    .minimum_version_id = 53,')
    anchor = '        VMSTATE_BOOL(z62_raw_stop_control, NikonZ72BootConfig),'
    fields = '''
        VMSTATE_BOOL(z62_paired_ingress, NikonZ72BootConfig),
        VMSTATE_BOOL(paired_ingress_active, NikonZ72BootConfig),
        VMSTATE_BOOL(paired_ingress_owns_source, NikonZ72BootConfig),
        VMSTATE_UINT32(paired_ingress_reason, NikonZ72BootConfig),
        VMSTATE_UINT64(paired_ingress_attempts, NikonZ72BootConfig),
        VMSTATE_UINT64(paired_ingress_frames, NikonZ72BootConfig),
        VMSTATE_UINT64(paired_ingress_bytes, NikonZ72BootConfig),
        VMSTATE_UINT64(paired_ingress_rejected, NikonZ72BootConfig),
        VMSTATE_UINT64(paired_ingress_blocked, NikonZ72BootConfig),
        VMSTATE_UINT64(paired_ingress_dma_ns, NikonZ72BootConfig),
        VMSTATE_UINT64_ARRAY(paired_ingress_tags, NikonZ72BootConfig, 4),
        VMSTATE_TIMER_PTR(paired_ingress_timer, NikonZ72BootConfig),'''
    board = replace(board, anchor, anchor+fields)
    board = replace(board, '    if (video_post_load(s)) { return -EINVAL; }', '''    if (video_post_load(s)) { return -EINVAL; }
    if (s->paired_ingress_reason > PAIRED_SEQUENCE ||
        s->paired_ingress_frames > UINT64_MAX/(4ull*Z62_PAIRED_SCENE_BYTES) ||
        s->paired_ingress_bytes != s->paired_ingress_frames*4ull*Z62_PAIRED_SCENE_BYTES ||
        (s->paired_ingress_active && (!s->z62_paired_ingress || !s->master_role ||
                                     !timer_pending(s->paired_ingress_timer))) ||
        (s->paired_ingress_owns_source && (!s->z62_paired_ingress || !s->preview_source_valid))) return -EINVAL;''')
    anchor = '        DEFINE_PROP_BOOL("z62-raw-stop-control", NikonZ72BootConfig, z62_raw_stop_control, false),'
    board = replace(board, anchor, anchor+'\n        DEFINE_PROP_BOOL("z62-paired-ingress", NikonZ72BootConfig, z62_paired_ingress, false),')
    board = replace(board, '    preview_realize(s, root);', '''    if (s->z62_paired_ingress && (!s->z62_preview || !s->z62_preview_results || !s->z62_raw_stop_control)) {
        error_setg(errp, "z62-paired-ingress needs preview/results and explicit RAW stop control");
        return;
    }
    preview_realize(s, root);''')
    anchor = '    sysbus_realize_and_unref(SYS_BUS_DEVICE(input_config), &error_fatal);'
    board = replace(board, anchor, anchor+'\n    boot_config->paired_input = input_config;')
    result['hw/arm/nikon-z72.c'] = board
    source = result['hw/arm/nikon-z72-input-config.c']
    source = replace(source, '#include "nikon-z62-scene-state.h"',
                     '#include "nikon-z62-scene-state.h"\n#include "nikon-z62-paired-ingress-api.h"')
    source = replace(source, '#include "nikon-z62-scene-file.h"', '''#include "nikon-z62-scene-file.h"

bool z62_paired_scene_copy(DeviceState *dev, uint8_t *pixels, uint64_t tags[4])
{
    Z72InputConfig *s=Z72_INPUT_CONFIG(dev);
    G_STATIC_ASSERT(Z62_SCENE_BYTES==Z62_PAIRED_SCENE_BYTES);
    if (!s->z62_layout || !s->scene.enabled || !s->scene.valid) return false;
    tags[0]=s->scene.epoch; tags[1]=s->scene.publish_id;
    tags[2]=s->scene.frame_id; tags[3]=s->scene.time_ns;
    memcpy(pixels,s->scene.pixels,Z62_SCENE_BYTES);
    return true;
}

bool z62_paired_scene_used(DeviceState *dev, const uint64_t tags[4])
{
    Z72InputConfig *s=Z72_INPUT_CONFIG(dev);
    if (!s->scene.enabled || !s->scene.valid || tags[0]!=s->scene.epoch ||
        tags[1]!=s->scene.publish_id || tags[2]!=s->scene.frame_id || tags[3]!=s->scene.time_ns) return false;
    scene_used(s);
    return true;
}
''')
    result['hw/arm/nikon-z72-input-config.c'] = source
    preview = result['hw/arm/nikon-z62-preview.h']
    anchor = '#include "nikon-z62-video-isp.h"'
    preview = replace(preview, anchor, anchor+'\n#include "nikon-z62-paired-ingress.h"')
    preview = replace(preview, '    s->preview_source_seq=s->raw_stream_frames;', '''    if (s->z62_paired_ingress) {
        uint64_t previous=MAX(s->preview_source_seq,s->preview_last_seq);
        if (previous==UINT64_MAX) { s->preview_source_valid=false; return; }
        s->preview_source_seq=previous+1;
        s->paired_ingress_owns_source=false;
    } else {
        s->preview_source_seq=s->raw_stream_frames;
    }''')
    preview = replace(preview, '    preview_schedule(s);\n}\n\nstatic uint64_t preview_raw_read',
                      '    paired_ingress_control(s,0x20100000+offset,value);\n    preview_schedule(s);\n}\n\nstatic uint64_t preview_raw_read')
    preview = replace(preview, '    preview_irq99(s);\n    preview_schedule(s);\n}',
                      '    paired_ingress_control(s,0x20380000+offset,value);\n    preview_irq99(s);\n    preview_schedule(s);\n}')
    preview = replace(preview, 'static void preview_reset(NikonZ72BootConfig *s)\n{',
                      'static void preview_reset(NikonZ72BootConfig *s)\n{\n    paired_ingress_reset(s);')
    preview = replace(preview, 'static void preview_init(Object *obj)\n{',
                      'static void preview_init(Object *obj)\n{\n    paired_ingress_init(obj);')
    preview = replace(preview, 'static void preview_finalize(NikonZ72BootConfig *s)\n{',
                      'static void preview_finalize(NikonZ72BootConfig *s)\n{\n    timer_del(s->paired_ingress_timer); timer_free(s->paired_ingress_timer);')
    result['hw/arm/nikon-z62-preview.h'] = preview
    result.update({'hw/arm/'+name: path.read_text(encoding='utf-8') for name, path in HEADERS.items()})
    return {name: value.encode('utf-8') for name, value in result.items()}


def apply_source(source):
    source = Path(source)
    if not source.resolve().is_relative_to(WORK.resolve()):
        raise ValueError('Paired input must use its independent workspace')
    output = render({name: (source/name).read_bytes() for name in INPUTS})
    for name, data in output.items():
        (source/name).write_bytes(data)
    return output
