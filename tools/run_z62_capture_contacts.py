"""Identity and configuration helpers for the isolated r13 research kernel."""
import json
from pathlib import Path
import run_z62_preview as parent
import z62_capture_contacts_device as device

DEFAULT_QEMU = device.WORK / 'runtime/qemu-system-arm.exe'


def verify_build(qemu):
    qemu = Path(qemu).resolve()
    prior = parent.verify_build(qemu)
    record = json.loads((qemu.parent.parent / 'capture-contacts-build-manifest.json').read_text(encoding='utf-8'))
    if (record.get('schema') != 1 or record.get('version') != device.VERSION or
            record.get('capture_contacts_device') != device.identity() or
            record.get('binary_sha256') != prior['binary_sha256']):
        raise ValueError('Capture contacts source or binary identity mismatch')
    return record


def configure_command(command, enabled=True):
    result = list(command)
    value = 'nikon-z72-boot-config.z62-capture-contacts=on'
    if enabled and value not in result:
        result += ['-global', value]
    return result
