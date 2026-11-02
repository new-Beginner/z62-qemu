"""Identity verification for the independent r23 C-level scene-source kernel."""
import json
from pathlib import Path
import run_z62_analog_input as parent
import z62_scene_source_device as device

DEFAULT_QEMU = device.WORK / 'runtime/qemu-system-arm.exe'


def verify_build(qemu=DEFAULT_QEMU):
    qemu = Path(qemu).resolve()
    previous = parent.verify_build(qemu)
    record = json.loads((qemu.parent.parent / 'scene-source-build-manifest.json').read_text(encoding='utf-8'))
    if (record.get('schema') != 1 or record.get('version') != device.VERSION or
            record.get('scene_source_device') != device.identity() or
            record.get('binary_sha256') != previous['binary_sha256']):
        raise ValueError('Scene source or binary identity mismatch')
    return record
