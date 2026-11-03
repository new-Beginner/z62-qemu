"""Identity and opt-in for the captured post-video photo layout."""
import json
from pathlib import Path
import run_z62_grid_geometry as parent
import reference_updates as reference
import z62_photo_results_device as device

DEFAULT_QEMU=device.WORK/'runtime/qemu-system-arm.exe'


def verify_build(qemu=DEFAULT_QEMU):
    qemu=Path(qemu).resolve()
    prior=parent.verify_build(qemu)
    record=json.loads((qemu.parent.parent/'photo-results-build-manifest.json').read_text(encoding='utf-8'))
    if (record.get('schema')!=1 or record.get('version')!=device.VERSION or
        record.get('photo_results_device')!=device.identity() or record.get('binary_sha256')!=prior['binary_sha256']):
        raise ValueError('Photo result source or binary identity mismatch')
    base=json.loads((qemu.parent.parent/'reference-build-manifest.json').read_text(encoding='utf-8'))
    for name,digest in record['generated_source_sha256'].items():
        if reference.sha((Path(base['source'])/'hw/arm'/name).read_bytes())!=digest:
            raise ValueError('Built photo result source changed: '+name)
    return record


def configure_command(command,geometry=True,retained=False,photo=True):
    result=parent.configure_command(command,geometry,retained)
    flag='nikon-z72-boot-config.z62-photo-result-layouts=on'
    if photo and flag not in result: result+=['-global',flag]
    return result
