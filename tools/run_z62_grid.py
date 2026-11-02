"""Identity and opt-in for the numerical bank0 kernel."""
import json
from pathlib import Path
import reference_updates as reference
import run_z62_preview_results_format as parent
import z62_grid_device as device

DEFAULT_QEMU=device.WORK/'runtime/qemu-system-arm.exe'


def verify_build(qemu=DEFAULT_QEMU):
    qemu=Path(qemu).resolve()
    prior=parent.verify_build(qemu)
    work=qemu.parent.parent
    record=json.loads((work/'grid-build-manifest.json').read_text(encoding='utf-8'))
    if (record.get('schema')!=1 or record.get('version')!=device.VERSION or
        record.get('grid_device')!=device.identity() or record.get('binary_sha256')!=prior['binary_sha256']):
        raise ValueError('Numerical grid source or binary identity mismatch')
    source=Path(json.loads((work/'reference-build-manifest.json').read_text(encoding='utf-8'))['source'])/'hw/arm'
    for name,h in record['generated_source_sha256'].items():
        if reference.sha((source/name).read_bytes())!=h: raise ValueError('Built grid source changed: '+name)
    return record


def configure_command(command,enabled=False):
    result=list(command)
    flag='nikon-z72-boot-config.z62-grid-process=on'
    if enabled and flag not in result: result+=['-global',flag]
    return result
