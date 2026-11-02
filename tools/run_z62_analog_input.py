"""Build identity for the r21 runtime analogue-input research kernel."""
import json
from pathlib import Path
import run_z62_continuous_stats as parent
import z62_analog_input_device as device

DEFAULT_QEMU=device.WORK/'runtime/qemu-system-arm.exe'


def verify_build(qemu=DEFAULT_QEMU):
    qemu=Path(qemu).resolve()
    previous=parent.verify_build(qemu)
    record=json.loads((qemu.parent.parent/'analog-input-build-manifest.json').read_text(encoding='utf-8'))
    if (record.get('schema') != 1 or record.get('version') != device.VERSION or
            record.get('analog_input_device') != device.identity() or
            record.get('binary_sha256') != previous['binary_sha256']):
        raise ValueError('Runtime analogue input source or binary identity mismatch')
    return record
