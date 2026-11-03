"""r62 opt-in RAW +0C stop admission; preserve frozen r60 by default."""
from pathlib import Path
import reference_updates as reference

ROOT = Path(__file__).resolve().parents[1]
VERSION = '2026.11.03-r62'
WORK = ROOT/'.build'/('z62-raw-stop-control-'+VERSION)
INPUTS = {'nikon-z72.c': 'de50e37c072d69a253c5d0e414f4139c7d86fe25ef106e0a973fa7a211aef623',
          'nikon-z62-raw-stream.h': 'b8a3cac25f78bc92f0b11467fb32b7d95438ad95d6e0f6db1c528a436fc6f0c3'}


def identity():
    return {'schema': 1, 'version': VERSION, 'input_sha256': INPUTS,
            'adapter_sha256': reference.sha(Path(__file__).read_bytes()), 'default_enabled': False,
            'stop_address': '0x2006800c', 'raw_stop_mask': 0x200, 'vmstate_version': 52,
            'new_completion_produced': False, 'physical_protocol_equivalent': False,
            'guest_software_patched': False}


def render(files):
    for name, digest in INPUTS.items():
        if reference.sha(files[name]) != digest: raise ValueError('RAW stop requires frozen r60 '+name)
    result = {name: raw.decode('utf-8') for name, raw in files.items()}
    replace = reference.replace_once
    board = replace(result['nikon-z72.c'], '    bool z62_statistics_observe;',
                    '    bool z62_statistics_observe;\n    bool z62_raw_stop_control;')
    board = replace(board, '    .version_id = 51,\n    .minimum_version_id = 51,',
                    '    .version_id = 52,\n    .minimum_version_id = 52,')
    anchor = '        VMSTATE_BOOL(z62_statistics_observe, NikonZ72BootConfig),'
    board = replace(board, anchor, anchor+'\n        VMSTATE_BOOL(z62_raw_stop_control, NikonZ72BootConfig),')
    anchor = '        DEFINE_PROP_BOOL("z62-statistics-observe", NikonZ72BootConfig, z62_statistics_observe, false),'
    board = replace(board, anchor, anchor+'\n        DEFINE_PROP_BOOL("z62-raw-stop-control", NikonZ72BootConfig, z62_raw_stop_control, false),')
    result['nikon-z72.c'] = board
    result['nikon-z62-raw-stream.h'] = replace(result['nikon-z62-raw-stream.h'],
        '    } else if ((address == 0x20068014 || address == 0x20068018) && (value & 0x200)) {',
        '    } else if ((address == 0x20068014 || address == 0x20068018 ||\n'
        '                (s->z62_raw_stop_control && address == 0x2006800c)) && (value & 0x200)) {')
    return {name: data.encode('utf-8') for name, data in result.items()}


def apply_source(source):
    root = Path(source)/'hw/arm'
    output = render({name: (root/name).read_bytes() for name in INPUTS})
    for name, data in output.items(): (root/name).write_bytes(data)
    return output
