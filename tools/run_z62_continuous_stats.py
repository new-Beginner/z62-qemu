"""Identity and explicit configuration for the isolated r18 research kernel."""
import json
from pathlib import Path
import run_z62_raw_boundary as parent
import z62_continuous_stats_device as device

DEFAULT_QEMU = device.WORK / 'runtime/qemu-system-arm.exe'


def verify_build(qemu):
    qemu = Path(qemu).resolve()
    previous = parent.verify_build(qemu)
    record = json.loads((qemu.parent.parent / 'continuous-stats-build-manifest.json').read_text(encoding='utf-8'))
    if (record.get('schema') != 1 or record.get('version') != device.VERSION or
            record.get('continuous_statistics_device') != device.identity() or
            record.get('binary_sha256') != previous['binary_sha256']):
        raise ValueError('Continuous statistics source or binary identity mismatch')
    return record


def configure_command(command, enabled=True):
    result = list(command)
    if enabled:
        for value in ('nikon-z72-boot-config.z62-finite-stats=on',
                      'nikon-z72-input-config.functional-continuous-stats=on'):
            if value not in result:
                result += ['-global', value]
    return result
