# SPDX-License-Identifier: GPL-2.0-or-later
"""Build independent native Windows Z62 functional RAW experiment (no firmware)."""
import argparse
import json
from pathlib import Path
import sys
import build_reference_qemu as reference
import reference_updates
import z62_functional_device as functional

ROOT = reference.ROOT
DEFAULT_WORK = ROOT / '.build' / ('z62-functional-' + functional.VERSION)
OLD_MANIFEST = ROOT / '.build/z62-reference-2026.10.27-r1/reference-build-manifest.json'


def build(args):
    work = reference.guard_workspace(args.work_dir, 'z62', updates=True)
    if sys.platform != 'win32':
        raise ValueError('Requires native Windows Python + MSYS2 UCRT64')
    msys = args.msys2_dir or Path(json.loads(OLD_MANIFEST.read_text(encoding='utf-8'))['msys2_dir'])
    msys = msys.resolve()
    for name in ('usr/bin/bash.exe', 'ucrt64/bin/gcc.exe', 'ucrt64/bin/objdump.exe'):
        if not (msys / name).is_file():
            raise ValueError('Missing toolchain file: ' + str(msys / name))
    repo = reference.verify_repository('z62')
    upstream = reference.upstream
    archive = ROOT / '.build/downloads' / f'qemu-{upstream.QEMU_VERSION}.tar.xz'
    if not archive.is_file() or upstream.digest(archive) != upstream.ARCHIVE_SHA256:
        raise ValueError('Missing or invalid cached QEMU archive')
    expected_functional = functional.identity()
    expected_reference = reference_updates.identity()
    work.mkdir(parents=True, exist_ok=True)
    with (work / reference.MARKER).open('x', encoding='utf-8') as handle:
        json.dump(reference.identity('z62', True), handle, indent=2)
    donor = work / 'donor'
    donor_hashes = reference.snapshot_donor(repo, donor)
    reference.verify_repository('z62')
    source = upstream.unpack(archive, work / 'source')
    reference.prepare_source(source, donor)
    reference_updates.apply_source(source)
    functional.apply_source(source)
    source_hashes = reference.tree_hashes(source)
    binary = reference.run_build(source, work / 'build', msys, args.jobs)
    reference.verify_devices(work / 'build')
    runtime = work / 'runtime'
    runtime.mkdir(exist_ok=False)
    dlls = upstream.stage_windows(binary, msys, runtime)
    staged = runtime / binary.name
    checks = reference.smoke_checks(staged, 'z62')
    reference.verify_repository('z62')
    if functional.identity() != expected_functional or reference_updates.identity() != expected_reference:
        raise ValueError('Adapter changed during build; refusing manifest')
    manifest = {**reference.identity('z62', True),
                'functional_device': expected_functional,
                'source': str(source), 'build': str(work / 'build'),
                'runtime': str(runtime), 'binary': str(staged), 'jobs': args.jobs,
                'binary_sha256': upstream.digest(staged), 'binary_bytes': staged.stat().st_size,
                'runtime_dll_sha256': dlls, 'donor_file_sha256': donor_hashes,
                'prepared_source_file_sha256': source_hashes,
                'builder_sha256': upstream.digest(Path(__file__)),
                'upstream_builder_sha256': upstream.digest(ROOT / 'tools/build_qemu.py'),
                'msys2_dir': str(msys), 'checks': checks,
                'firmware_run': False, 'guest_patched': False, 'cpu_patched': False}
    with (work / 'reference-build-manifest.json').open('x', encoding='utf-8') as handle:
        json.dump(manifest, handle, indent=2)
    extra = {key: manifest[key] for key in ('binary', 'binary_sha256', 'reference_updates',
             'functional_device', 'builder_sha256', 'msys2_dir', 'donor_commit')}
    extra.update(schema=1, version=functional.VERSION,
                 generated_functional_sha256={name: source_hashes['hw/arm/' + name]
                    for name in (*functional.INPUTS, functional.HEADER.name)})
    with (work / 'functional-build-manifest.json').open('x', encoding='utf-8') as handle:
        json.dump(extra, handle, indent=2)
    return extra


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work-dir', type=Path, default=DEFAULT_WORK)
    parser.add_argument('--msys2-dir', type=Path)
    parser.add_argument('--jobs', type=int, default=12)
    args = parser.parse_args()
    if not 1 <= args.jobs <= 32:
        parser.error('--jobs must be 1..32')
    print(json.dumps(build(args), indent=2), flush=True)


if __name__ == '__main__':
    main()
