"""Identity verification for r24 file-mailbox scene transport."""
import json
from pathlib import Path
import run_z62_scene_source as parent
import z62_scene_file_device as device

DEFAULT_QEMU = device.WORK / 'runtime/qemu-system-arm.exe'


def verify_build(qemu=DEFAULT_QEMU):
    qemu = Path(qemu).resolve()
    prior = parent.verify_build(qemu)
    record = json.loads((qemu.parent.parent / 'scene-file-build-manifest.json').read_text(encoding='utf-8'))
    if (record.get('schema') != 1 or record.get('version') != device.VERSION or
            record.get('scene_file_device') != device.identity() or record.get('binary_sha256') != prior['binary_sha256']):
        raise ValueError('Scene file transport or binary identity mismatch')
    return record
