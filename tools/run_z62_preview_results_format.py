"""Verify r47b without invalidating the preserved r47 implementation."""
import json
from pathlib import Path
import run_z62_preview_results as parent
import z62_preview_results_format_device as device
import reference_updates as reference

DEFAULT_QEMU = device.WORK/'runtime/qemu-system-arm.exe'
configure_command = parent.configure_command


def verify_build(qemu=DEFAULT_QEMU):
    qemu = Path(qemu).resolve()
    prior = parent.verify_build(qemu)
    work = qemu.parent.parent
    m = json.loads((work/'preview-results-format-build-manifest.json').read_text(encoding='utf-8'))
    if (m.get('schema') != 1 or m.get('version') != device.VERSION or
            m.get('format_device') != device.identity() or m.get('binary_sha256') != prior['binary_sha256']):
        raise ValueError('Preview result format source or binary identity mismatch')
    base = json.loads((work/'reference-build-manifest.json').read_text(encoding='utf-8'))
    if reference.sha((Path(base['source'])/'hw/arm'/device.NAME).read_bytes()) != m['generated_profile_sha256']:
        raise ValueError('Built result format profile changed')
    return m
