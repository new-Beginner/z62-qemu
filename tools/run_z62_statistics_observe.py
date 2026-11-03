"""r60 identity and explicit diagnostic opt-in over the r59b C video profile."""
import json
from pathlib import Path
import run_z62_video_isp_format as parent
import reference_updates as reference
import z62_statistics_observe_device as device

DEFAULT_QEMU = device.WORK/'runtime/qemu-system-arm.exe'


def verify_build(qemu=DEFAULT_QEMU):
    qemu = Path(qemu).resolve(); prior = parent.verify_build(qemu)
    record = json.loads((qemu.parent.parent/'statistics-observe-build-manifest.json').read_text(encoding='utf-8'))
    if (record.get('schema') != 1 or record.get('version') != device.VERSION or
        record.get('statistics_observe_device') != device.identity() or record.get('binary_sha256') != prior['binary_sha256']):
        raise ValueError('Statistics observer source or binary differs')
    base = json.loads((qemu.parent.parent/'reference-build-manifest.json').read_text(encoding='utf-8'))
    for name, digest in record['generated_source_sha256'].items():
        if reference.sha((Path(base['source'])/'hw/arm'/name).read_bytes()) != digest:
            raise ValueError('Built observer source changed: '+name)
    return record


def configure_command(command, geometry=True, retained=False, video=False, origin=None, observe=False):
    if any('nikon-z72-boot-config.z62-statistics-observe=' in item for item in command):
        raise ValueError('Observer option already supplied')
    result = parent.configure_command(command, geometry, retained, video, origin)
    if observe: result += ['-global', 'nikon-z72-boot-config.z62-statistics-observe=on']
    return result
