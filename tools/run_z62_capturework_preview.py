"""Verify the independent four-real-frame CW preview source build."""
import json
from pathlib import Path
import run_z62_readout_statistics as parent
import z62_capturework_preview_device as device
import reference_updates as reference

DEFAULT_QEMU=device.WORK/'runtime/qemu-system-arm.exe'


def verify_build(qemu=DEFAULT_QEMU):
    qemu=Path(qemu).resolve();previous=parent.verify_build(qemu);work=qemu.parent.parent
    record=json.loads((work/'capturework-preview-build-manifest.json').read_text(encoding='utf-8'))
    if record['version']!=device.VERSION or record['capturework_preview_device']!=device.identity() or record['binary_sha256']!=previous['binary_sha256']:
        raise ValueError('CW preview source/binary identity differs')
    source=Path(json.loads((work/'reference-build-manifest.json').read_text(encoding='utf-8'))['source'])
    for name,sha in record['generated_source_sha256'].items():
        if reference.sha((source/name).read_bytes())!=sha:raise ValueError('Bound CW preview source changed: '+name)
    return record
