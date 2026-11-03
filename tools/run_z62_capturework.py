"""Source-bound r89 verification/configuration helpers; not a promoted UI entry."""
import argparse
import json
from pathlib import Path

import reference_updates as reference
import run_z62_output_lineage as parent
import z62_capturework_device as device

DEFAULT_QEMU=device.WORK/'runtime/qemu-system-arm.exe'


def verify_build(qemu=DEFAULT_QEMU):
    qemu=Path(qemu).resolve(); previous=parent.verify_build(qemu)
    work=qemu.parent.parent
    record=json.loads((work/'capturework-build-manifest.json').read_text(encoding='utf-8'))
    if (record.get('schema')!=1 or record.get('version')!=device.VERSION or
        record.get('capturework_device')!=device.identity() or record['binary_sha256']!=previous['binary_sha256']):
        raise ValueError('CaptureWork source or binary differs')
    root=json.loads((work/'reference-build-manifest.json').read_text(encoding='utf-8'))
    for name,expected in record['generated_source_sha256'].items():
        if reference.sha((Path(root['source'])/name).read_bytes())!=expected:
            raise ValueError('Bound CaptureWork source changed: '+name)
    return record


def configure_command(command,enabled=False):
    if any('nikon-z72-input-config.z62-capturework=' in value for value in command):
        raise ValueError('CaptureWork option already supplied')
    if enabled and any('nikon-z72-boot-config.z62-paired-ingress=on' in value or
        'nikon-z72-input-config.laboratory-metadata-completion=on' in value for value in command):
        raise ValueError('CaptureWork cannot share output ownership with paired ingress or metadata-only completion')
    return list(command)+(['-global','nikon-z72-input-config.z62-capturework=on'] if enabled else [])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--qemu',type=Path,default=DEFAULT_QEMU)
    args=parser.parse_args(); record=verify_build(args.qemu)
    print(json.dumps({'version':record['version'],'binary_sha256':record['binary_sha256'],
        'source_binding_verified':True,'original_firmware_executed':False,'camera_accessed':False}),flush=True)
