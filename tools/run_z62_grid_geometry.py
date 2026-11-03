"""Identity and independent opt-ins for r52 geometry and retained-data work."""
import json
from pathlib import Path
import run_z62_grid as parent
import reference_updates as reference
import z62_grid_geometry_device as device

DEFAULT_QEMU = device.WORK/'runtime/qemu-system-arm.exe'


def verify_build(qemu=DEFAULT_QEMU):
    qemu = Path(qemu).resolve()
    prior = parent.verify_build(qemu)
    record = json.loads((qemu.parent.parent/'grid-geometry-build-manifest.json').read_text(encoding='utf-8'))
    if (record.get('schema') != 1 or record.get('version') != device.VERSION or
            record.get('grid_geometry_device') != device.identity() or
            record.get('binary_sha256') != prior['binary_sha256']):
        raise ValueError('Grid geometry source or binary identity mismatch')
    base = json.loads((qemu.parent.parent/'reference-build-manifest.json').read_text(encoding='utf-8'))
    source = Path(base['source'])/'hw/arm'
    for name,digest in record['generated_source_sha256'].items():
        if reference.sha((source/name).read_bytes()) != digest:
            raise ValueError('Built grid geometry source changed: '+name)
    return record


def configure_command(command, geometry=True, retained=False):
    result = parent.configure_command(command, True)
    for enabled, name in ((geometry,'z62-grid-geometry'),(retained,'z62-grid-retained-input')):
        flag = 'nikon-z72-boot-config.'+name+'=on'
        if enabled and flag not in result:
            result += ['-global',flag]
    return result
