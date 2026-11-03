"""Explicit external-MAIN policy0 configuration on a separately bound r91."""
import json
from pathlib import Path
import run_z62_capturework as parent
import z62_capturework_policy_device as device
import reference_updates as reference

DEFAULT_QEMU=device.WORK/'runtime/qemu-system-arm.exe'


def verify_build(qemu=DEFAULT_QEMU):
    qemu=Path(qemu).resolve(); previous=parent.verify_build(qemu)
    work=qemu.parent.parent
    record=json.loads((work/'capturework-policy-build-manifest.json').read_text(encoding='utf-8'))
    if (record['version']!=device.VERSION or record['capturework_policy_device']!=device.identity() or
        record['binary_sha256']!=previous['binary_sha256']): raise ValueError('Policy source or binary differs')
    source=Path(json.loads((work/'reference-build-manifest.json').read_text(encoding='utf-8'))['source'])
    for name,expected in record['generated_source_sha256'].items():
        if reference.sha((source/name).read_bytes())!=expected: raise ValueError('Policy build source changed: '+name)
    return record


def configure_command(command,enabled=False):
    if any('nikon-z72-input-config.z62-capturework-policy0=' in value for value in command):
        raise ValueError('External MAIN policy already supplied')
    result=parent.configure_command(command,enabled)
    if enabled: result+=['-global','nikon-z72-input-config.z62-capturework-policy0=on']
    return result
