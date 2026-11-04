"""Source-bound r93 configuration helpers, never a promoted camera UI entry."""
import json
from pathlib import Path
import run_z62_capturework_statistics as parent
import z62_capture_group_device as device
import reference_updates as reference

DEFAULT_QEMU=device.WORK/'runtime/qemu-system-arm.exe'


def verify_build(qemu=DEFAULT_QEMU):
    qemu=Path(qemu).resolve();previous=parent.verify_build(qemu);work=qemu.parent.parent
    record=json.loads((work/'capture-group-build-manifest.json').read_text(encoding='utf-8'))
    if (record['version']!=device.VERSION or record['capture_group_device']!=device.identity() or
        record['binary_sha256']!=previous['binary_sha256']):raise ValueError('Group source or binary differs')
    source=Path(json.loads((work/'reference-build-manifest.json').read_text(encoding='utf-8'))['source'])
    for name,expected in record['generated_source_sha256'].items():
        if reference.sha((source/name).read_bytes())!=expected:raise ValueError('Group source changed: '+name)
    return record


def configure_command(command,enabled=False,statistics=True):
    if any('nikon-z72-input-config.z62-capture-group=' in x for x in command):raise ValueError('Group already supplied')
    result=parent.configure_command(command,enabled) if statistics else parent.parent.configure_command(command,enabled)
    if enabled:result+=['-global','nikon-z72-input-config.z62-capture-group=on']
    return result
