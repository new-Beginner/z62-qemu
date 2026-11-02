"""Identity and explicit opt-in for the independent r47 preview result kernel."""
import json
from pathlib import Path
import run_z62_scene_file as parent
import z62_preview_results_device as device
import reference_updates as reference

DEFAULT_QEMU = device.WORK/'runtime/qemu-system-arm.exe'


def verify_build(qemu=DEFAULT_QEMU):
    qemu = Path(qemu).resolve()
    prior = parent.verify_build(qemu)
    work = qemu.parent.parent
    record = json.loads((work/'preview-results-build-manifest.json').read_text(encoding='utf-8'))
    if (record.get('schema') != 1 or record.get('version') != device.VERSION or
            record.get('result_device') != device.identity() or
            record.get('binary_sha256') != prior['binary_sha256']):
        raise ValueError('Preview result device or binary identity mismatch')
    base = json.loads((work/'reference-build-manifest.json').read_text(encoding='utf-8'))
    for name, digest in record['generated_source_sha256'].items():
        if reference.sha((Path(base['source'])/'hw/arm'/name).read_bytes()) != digest:
            raise ValueError('Built preview result source changed: '+name)
    return record


def configure_command(command, enabled=False):
    result = list(command)
    flag = 'nikon-z72-boot-config.z62-preview-results=on'
    if enabled and flag not in result:
        result += ['-global', flag]
    return result
