"""Identity and opt-in configuration for committed C output provenance."""
import json
from pathlib import Path
import run_z62_paired_handoff as parent
import reference_updates as reference
import z62_output_lineage_device as device

DEFAULT_QEMU=device.WORK/'runtime/qemu-system-arm.exe'


def verify_build(qemu=DEFAULT_QEMU):
    qemu=Path(qemu).resolve(); previous=parent.verify_build(qemu)
    record=json.loads((qemu.parent.parent/'output-lineage-build-manifest.json').read_text(encoding='utf-8'))
    if (record.get('schema')!=1 or record.get('version')!=device.VERSION or
        record.get('output_lineage_device')!=device.identity() or record['binary_sha256']!=previous['binary_sha256']):
        raise ValueError('Output lineage source or binary differs')
    root=json.loads((qemu.parent.parent/'reference-build-manifest.json').read_text(encoding='utf-8'))
    for name,digest in record['generated_source_sha256'].items():
        if reference.sha((Path(root['source'])/name).read_bytes())!=digest:
            raise ValueError('Bound output-lineage source changed: '+name)
    return record


def configure_command(command, geometry=True, retained=False, video=False, origin=None,
                      observe=False, stop_control=False, paired=False, lineage=False):
    if lineage and not paired:
        raise ValueError('Output lineage requires explicit paired input profile')
    if any('nikon-z72-boot-config.z62-output-lineage=' in v for v in command):
        raise ValueError('Output lineage option already supplied')
    result=parent.configure_command(command,geometry,retained,video,origin,observe,stop_control,paired)
    if lineage:
        result+=['-global','nikon-z72-boot-config.z62-output-lineage=on']
    return result
