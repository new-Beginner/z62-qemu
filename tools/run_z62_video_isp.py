"""Identity and explicit C video-view opt-in; no implicit Nikon ROI choice."""
import json
from pathlib import Path
import run_z62_photo_results as parent
import reference_updates as reference
import z62_video_isp_device as device

DEFAULT_QEMU=device.WORK/'runtime/qemu-system-arm.exe'


def verify_build(qemu=DEFAULT_QEMU):
    qemu=Path(qemu).resolve();prior=parent.verify_build(qemu)
    record=json.loads((qemu.parent.parent/'video-isp-build-manifest.json').read_text(encoding='utf-8'))
    if record.get('schema')!=1 or record.get('version')!=device.VERSION or record.get('video_isp_device')!=device.identity() or record.get('binary_sha256')!=prior['binary_sha256']:
        raise ValueError('Video ISP source or binary identity differs')
    base=json.loads((qemu.parent.parent/'reference-build-manifest.json').read_text(encoding='utf-8'))
    for name,digest in record['generated_source_sha256'].items():
        if reference.sha((Path(base['source'])/'hw/arm'/name).read_bytes())!=digest:
            raise ValueError('Built video source changed: '+name)
    return record


def configure_command(command,geometry=True,retained=False,video=False,origin=None):
    if any('nikon-z72-boot-config.z62-video-' in item for item in command):
        raise ValueError('Video properties are already present')
    if video:
        if not isinstance(origin,(tuple,list)) or len(origin)!=2 or any(type(v) is not int or v%2 or not -4096<=v<=4096 for v in origin):
            raise ValueError('Explicit even C video origin is required')
    elif origin is not None:
        raise ValueError('Origin supplied while software video is disabled')
    result=parent.configure_command(list(command),geometry,retained,True)
    if video:
        result+=['-global','nikon-z72-boot-config.z62-video-isp=on',
                 '-global','nikon-z72-boot-config.z62-video-origin-x='+str(origin[0]),
                 '-global','nikon-z72-boot-config.z62-video-origin-y='+str(origin[1])]
    return result
