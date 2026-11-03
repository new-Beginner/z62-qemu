"""Independent r60 observation layer over frozen r59b; no device fix."""
from pathlib import Path
import reference_updates as reference

ROOT = Path(__file__).resolve().parents[1]
VERSION = '2026.11.03-r60'
WORK = ROOT/'.build'/('z62-statistics-observe-'+VERSION)
INPUTS = {'nikon-z72.c': '1a0cc4aa44c5ec24161f8eac7afd30f51cd00dddd65d9d68e3f55a1056d2282f',
          'nikon-z72-input-config.c': 'daf1338db741d15eb4638f6cefe1c7a9b80f1c825665fd1991f2feb62e34fd3d',
          'nikon-z62-finite-bridge.h': 'b348d05d858a1ac1e558a72f82767b36d6024e3f2dd451a99c25a34a3f59fa1b'}
HEADER = ROOT/'qemu/z62-statistics-observe/nikon-z62-statistics-observe.h'


def identity():
    return {'schema': 1, 'version': VERSION, 'input_sha256': INPUTS,
            'adapter_sha256': reference.sha(Path(__file__).read_bytes()),
            'header_sha256': reference.sha(HEADER.read_bytes()), 'default_enabled': False,
            'ring_capacity': 256, 'vmstate_version': 51, 'guest_software_patched': False,
            'completion_semantics_changed': False, 'pc_is_candidate_only': True}


def render(files):
    for name, digest in INPUTS.items():
        if reference.sha(files[name]) != digest: raise ValueError('Observer requires frozen r59b '+name)
    result = {name: data.decode('utf-8') for name, data in files.items()}
    replace = reference.replace_once
    board = result['nikon-z72.c']
    board = replace(board, '    bool z62_finite_stats, finite_started;', '''    bool z62_finite_stats, finite_started;
    bool z62_statistics_observe;
    uint64_t statistics_control_count, statistics_frame_calls, statistics_frame_pulses, statistics_commit_pulses;
    uint32_t statistics_address[256], statistics_value[256], statistics_mask[256], statistics_flags[256], statistics_pc[256];
    int32_t statistics_cpu[256];
    int64_t statistics_time[256];
    uint64_t statistics_frame[256];''')
    board = replace(board, '    .version_id = 50,\n    .minimum_version_id = 50,',
                    '    .version_id = 51,\n    .minimum_version_id = 51,')
    board = replace(board, '    s->finite_started = false;',
                    '    statistics_observe_reset(s);\n    s->finite_started = false;')
    board = replace(board, '    preview_init(obj);', '    preview_init(obj);\n    statistics_observe_init(obj);')
    anchor = '        VMSTATE_BOOL(finite_started, NikonZ72BootConfig),'
    fields = ['        VMSTATE_BOOL(z62_statistics_observe, NikonZ72BootConfig),']
    fields += ['        VMSTATE_UINT64('+name+', NikonZ72BootConfig),' for name in
               ('statistics_control_count', 'statistics_frame_calls', 'statistics_frame_pulses', 'statistics_commit_pulses')]
    fields += ['        VMSTATE_'+kind+'_ARRAY('+name+', NikonZ72BootConfig, 256),' for kind, name in
               [('UINT32', 'statistics_'+x) for x in ('address', 'value', 'mask', 'flags', 'pc')]+
               [('INT32', 'statistics_cpu'), ('INT64', 'statistics_time'), ('UINT64', 'statistics_frame')]]
    board = replace(board, anchor, anchor+'\n'+'\n'.join(fields))
    anchor = '        DEFINE_PROP_BOOL("z62-video-isp", NikonZ72BootConfig, z62_video_isp, false),'
    board = replace(board, anchor, anchor+'\n        DEFINE_PROP_BOOL("z62-statistics-observe", NikonZ72BootConfig, z62_statistics_observe, false),')
    result['nikon-z72.c'] = board
    bridge = result['nikon-z62-finite-bridge.h']
    bridge = replace(bridge, 'static void finite_bridge_control(', 'static void finite_bridge_control_model(')
    bridge = replace(bridge, 'static void finite_bridge_frame(', 'static void finite_bridge_frame_model(')
    result['nikon-z62-finite-bridge.h'] = bridge+'\n#include "nikon-z62-statistics-observe.h"\n'
    device = result['nikon-z72-input-config.c']
    getters = []
    props = []
    for name in ('enabled', 'active', 'rearm', 'clock_level'):
        getters.append('static bool observe_continuous_'+name+'_get(Object *obj, Error **errp)\n'
                       '{ return Z72_INPUT_CONFIG(obj)->continuous_'+name+'; }')
        props.append('    object_property_add_bool(obj, "continuous-'+name.replace('_', '-')+'", observe_continuous_'+name+'_get, NULL);')
    device = replace(device, '#include "nikon-z62-continuous-stats.h"',
                     '#include "nikon-z62-continuous-stats.h"\n'+'\n'.join(getters))
    device = replace(device, '    scene_qom_init(obj);', '\n'.join(props)+'\n    scene_qom_init(obj);')
    result['nikon-z72-input-config.c'] = device
    result[HEADER.name] = HEADER.read_text(encoding='utf-8')
    return {name: data.encode('utf-8') for name, data in result.items()}


def apply_source(source):
    root = Path(source)/'hw/arm'
    output = render({name: (root/name).read_bytes() for name in INPUTS})
    for name, data in output.items(): (root/name).write_bytes(data)
    return output
