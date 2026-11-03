"""Identity and explicit configuration for level-C paired input."""
import json
from pathlib import Path
import run_z62_mmio_filter as parent
import reference_updates as reference
import z62_paired_ingress_device as device

DEFAULT_QEMU=device.WORK/'runtime/qemu-system-arm.exe'


def verify_build(qemu=DEFAULT_QEMU):
    qemu=Path(qemu).resolve(); prior=parent.verify_build(qemu)
    record=json.loads((qemu.parent.parent/'paired-ingress-build-manifest.json').read_text(encoding='utf-8'))
    if (record.get('schema')!=1 or record.get('version')!=device.VERSION or
        record.get('paired_ingress_device')!=device.identity() or record.get('binary_sha256')!=prior['binary_sha256']):
        raise ValueError('Paired software input source or binary differs')
    base=json.loads((qemu.parent.parent/'reference-build-manifest.json').read_text(encoding='utf-8'))
    for name,digest in record['generated_source_sha256'].items():
        if reference.sha((Path(base['source'])/name).read_bytes())!=digest:
            raise ValueError('Built paired software source changed: '+name)
    return record


def configure_command(command, geometry=True, retained=False, video=False, origin=None,
                      observe=False, stop_control=False, paired=False):
    if paired and not stop_control:
        raise ValueError('Paired software input requires explicit RAW stop control')
    result=parent.configure_command(command,geometry,retained,video,origin,observe,stop_control)
    if paired:
        if any('nikon-z72-boot-config.z62-paired-ingress=' in v for v in result):
            raise ValueError('Paired input option already supplied')
        result+=['-global','nikon-z72-boot-config.z62-paired-ingress=on']
    return result
