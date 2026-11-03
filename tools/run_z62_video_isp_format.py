"""Verified r59b binary; preserve the r59 explicit-origin command contract."""
import json
from pathlib import Path
import run_z62_video_isp as parent
import reference_updates as reference
import z62_video_isp_format_device as device

DEFAULT_QEMU=device.WORK/'runtime/qemu-system-arm.exe'
configure_command=parent.configure_command


def verify_build(qemu=DEFAULT_QEMU):
    qemu=Path(qemu).resolve();prior=parent.verify_build(qemu)
    record=json.loads((qemu.parent.parent/'video-isp-format-build-manifest.json').read_text(encoding='utf-8'))
    if record.get('schema')!=1 or record.get('version')!=device.VERSION or record.get('video_isp_format_device')!=device.identity() or record.get('binary_sha256')!=prior['binary_sha256']:
        raise ValueError('Video ring source or binary differs')
    base=json.loads((qemu.parent.parent/'reference-build-manifest.json').read_text(encoding='utf-8'))
    for name,digest in record['generated_source_sha256'].items():
        if reference.sha((Path(base['source'])/'hw/arm'/name).read_bytes())!=digest:
            raise ValueError('Built video ring source changed: '+name)
    return record
