"""Identity for the r66 ownership correction over the same opt-in C input."""
import json
from pathlib import Path
import run_z62_paired_ingress as parent
import reference_updates as reference
import z62_paired_handoff_device as device

DEFAULT_QEMU=device.WORK/'runtime/qemu-system-arm.exe'
configure_command=parent.configure_command


def verify_build(qemu=DEFAULT_QEMU):
    qemu=Path(qemu).resolve(); prior=parent.verify_build(qemu)
    record=json.loads((qemu.parent.parent/'paired-handoff-build-manifest.json').read_text(encoding='utf-8'))
    if (record.get('schema')!=1 or record.get('version')!=device.VERSION or
        record.get('paired_handoff_device')!=device.identity() or record.get('binary_sha256')!=prior['binary_sha256']):
        raise ValueError('Handoff source or binary identity differs')
    base=json.loads((qemu.parent.parent/'reference-build-manifest.json').read_text(encoding='utf-8'))
    for name,digest in record['generated_source_sha256'].items():
        if reference.sha((Path(base['source'])/name).read_bytes())!=digest:
            raise ValueError('Bound handoff source changed: '+name)
    return record
