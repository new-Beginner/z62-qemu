"""Identity/configuration for isolated r17; no default console promotion."""
import json
from pathlib import Path
import run_z62_capture_contacts as parent
import z62_raw_boundary_device as device

DEFAULT_QEMU = device.WORK / 'runtime/qemu-system-arm.exe'


def verify_build(qemu):
    qemu = Path(qemu).resolve()
    prior = parent.verify_build(qemu)
    record = json.loads((qemu.parent.parent / 'raw-boundary-build-manifest.json').read_text(encoding='utf-8'))
    if (record.get('schema') != 1 or record.get('version') != device.VERSION or
            record.get('raw_boundary_device') != device.identity() or
            record.get('binary_sha256') != prior['binary_sha256']):
        raise ValueError('RAW boundary source or binary identity mismatch')
    return record


def configure_command(command, enabled=True):
    result = list(command)
    option = 'nikon-z72-boot-config.z62-raw-boundary=on'
    if enabled and option not in result:
        result += ['-global', option]
    return result
