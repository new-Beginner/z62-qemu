"""r59b qualifies the actually unused MAIN second ring; WORK still mirrors."""
from pathlib import Path
import reference_updates as reference

ROOT=Path(__file__).resolve().parents[1]
VERSION='2026.11.03-r59b'
WORK=ROOT/'.build'/('z62-video-isp-format-'+VERSION)
INPUTS={'nikon-z72.c':'2ccfc050d84aab9381d43bf69bfe1a88188d3f8c1b68015a25c96d1cf4e4035a',
        'nikon-z62-video-isp.h':'20b0d2c8648f1b4d61da5e6461b66eb94bee8ee88622bf61e7cd78b9a04dbc8e'}


def identity():
    return {'schema':1,'version':VERSION,'input_sha256':INPUTS,
            'adapter_sha256':reference.sha(Path(__file__).read_bytes()),'default_enabled':False,
            'main_second_ring_requires_zero':True,'work_second_ring_requires_mirror':True,
            'physical_isp_equivalent':False,'guest_software_patched':False,'vmstate_version':50}


def render(files):
    for name,digest in INPUTS.items():
        if reference.sha(files[name])!=digest: raise ValueError('Video ring correction requires frozen r59 '+name)
    output={name:data.decode('utf-8') for name,data in files.items()}
    output['nikon-z72.c']=reference.replace_once(output['nikon-z72.c'],
        '    .version_id = 49,\n    .minimum_version_id = 49,',
        '    .version_id = 50,\n    .minimum_version_id = 50,')
    output['nikon-z62-video-isp.h']=reference.replace_once(output['nikon-z62-video-isp.h'],
        's->preview_raw[0x4a8/4+f]!=main[f][0] || s->preview_raw[0x4b8/4+f]!=main[f][1] ||',
        's->preview_raw[0x4a8/4+f]!=0 || s->preview_raw[0x4b8/4+f]!=0 ||')
    return {name:data.encode('utf-8') for name,data in output.items()}


def apply_source(source):
    root=Path(source)/'hw/arm'
    output=render({name:(root/name).read_bytes() for name in INPUTS})
    for name,data in output.items(): (root/name).write_bytes(data)
    return output
