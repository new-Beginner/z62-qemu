"""Identity for opt-in address-window diagnostics on the unchanged r62 models."""
import json
from pathlib import Path
import run_z62_raw_stop_control as parent
import reference_updates as reference
import z62_mmio_filter_device as device

DEFAULT_QEMU = device.WORK/'runtime/qemu-system-arm.exe'
configure_command = parent.configure_command


def verify_build(qemu=DEFAULT_QEMU):
    qemu = Path(qemu).resolve(); prior = parent.verify_build(qemu)
    record = json.loads((qemu.parent.parent/'mmio-filter-build-manifest.json').read_text(encoding='utf-8'))
    if (record.get('schema') != 1 or record.get('version') != device.VERSION or
        record.get('mmio_filter_device') != device.identity() or record.get('binary_sha256') != prior['binary_sha256']):
        raise ValueError('Filtered trace source or binary differs')
    base = json.loads((qemu.parent.parent/'reference-build-manifest.json').read_text(encoding='utf-8'))
    for name, digest in record['generated_source_sha256'].items():
        if reference.sha((Path(base['source'])/name).read_bytes()) != digest:
            raise ValueError('Built diagnostic source changed: '+name)
    return record
