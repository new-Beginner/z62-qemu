"""Explicit r92 source/linear-view statistics route; default UI is unchanged."""
import json
from pathlib import Path
import run_z62_capturework_policy as parent
import z62_capturework_statistics_device as device
import reference_updates as reference

DEFAULT_QEMU=device.WORK/'runtime/qemu-system-arm.exe'


def verify_build(qemu=DEFAULT_QEMU):
    qemu=Path(qemu).resolve(); previous=parent.verify_build(qemu); work=qemu.parent.parent
    record=json.loads((work/'capturework-statistics-build-manifest.json').read_text(encoding='utf-8'))
    if (record['version']!=device.VERSION or record['capturework_statistics_device']!=device.identity() or
        record['binary_sha256']!=previous['binary_sha256']): raise ValueError('Statistics source or binary differs')
    source=Path(json.loads((work/'reference-build-manifest.json').read_text(encoding='utf-8'))['source'])
    for name,expected in record['generated_source_sha256'].items():
        if reference.sha((source/name).read_bytes())!=expected: raise ValueError('Statistics build source changed: '+name)
    return record


def configure_command(command,enabled=False):
    if any('nikon-z72-input-config.z62-capturework-statistics=' in x for x in command):
        raise ValueError('CW statistics already supplied')
    result=parent.configure_command(command,enabled)
    if enabled:
        result+=['-global','nikon-z72-input-config.z62-capturework-statistics=on']
    return result
