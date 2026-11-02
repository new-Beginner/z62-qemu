# SPDX-License-Identifier: GPL-2.0-or-later
"""Build independent r6 from the fully hashed r5 prepared source snapshot."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import build_reference_qemu as reference
import run_z62_transaction as r5
import z62_capcom_device as capcom


def build(jobs, finish_staging=False):
    if sys.platform != 'win32':
        raise ValueError('Native Windows toolchain required')
    r5.verify_build(r5.DEFAULT_QEMU)
    old_root = r5.DEFAULT_QEMU.parent.parent
    old = json.loads((old_root / 'reference-build-manifest.json').read_text(encoding='utf-8'))
    work = capcom.WORK.resolve() if finish_staging else reference.guard_workspace(capcom.WORK, 'z62', updates=True)
    msys = Path(old['msys2_dir'])
    if not (msys / 'ucrt64/bin/gcc.exe').is_file():
        raise ValueError('Recorded MSYS2 compiler missing')
    expected = capcom.identity()
    source = work / 'source/qemu-10.2.4'
    original = Path(old['source']).resolve()
    hashes = old['prepared_source_file_sha256']
    if finish_staging:
        # Recover only the known post-link packaging failure. No source patch,
        # rebuild, completed runtime replacement or unverifiable resume.
        marker = json.loads((work / reference.MARKER).read_text(encoding='utf-8'))
        if marker != reference.identity('z62', True) or any(work.glob('*-build-manifest.json')):
            raise ValueError('Not an unfinished r6 staging attempt')
        source_hashes = dict(hashes)
        board = capcom.render((original / 'hw/arm/nikon-z72.c').read_bytes()).encode('utf-8')
        source_hashes['hw/arm/nikon-z72.c'] = hashlib.sha256(board).hexdigest()
        source_hashes['hw/arm/' + capcom.HEADER.name] = reference.upstream.digest(capcom.HEADER)
        print('Verifying unchanged source before packaging recovery', flush=True)
        for name, digest in source_hashes.items():
            path = source / name
            if not path.resolve().is_relative_to(source.resolve()) or path.is_symlink():
                raise ValueError('Unsafe recovery source')
            if reference.upstream.digest(path) != digest:
                raise ValueError('Recovery source mismatch: ' + name)
        binary = work / 'build/qemu-system-arm.exe'
        partial, archived = work / 'runtime', work / 'runtime-incomplete-objdump'
        if not partial.resolve().is_relative_to(work) or not archived.resolve().is_relative_to(work):
            raise ValueError('Recovery runtime escapes workspace')
        if partial.is_symlink() or (hasattr(partial, 'is_junction') and partial.is_junction()):
            raise ValueError('Linked partial runtime')
        if set(p.name for p in partial.iterdir()) != {'qemu-system-arm.exe'} or archived.exists():
            raise ValueError('Unexpected partial runtime contents')
        if reference.upstream.digest(partial / binary.name) != reference.upstream.digest(binary):
            raise ValueError('Partial binary differs from linked output')
        partial.rename(archived)
    else:
        work.mkdir(parents=True, exist_ok=False)
        (work / reference.MARKER).write_text(json.dumps(reference.identity('z62', True)), encoding='utf-8')
        print('Copying and verifying', len(hashes), 'r5 source files', flush=True)
        for index, (name, digest) in enumerate(hashes.items()):
            src, dest = original / name, source / name
            if not src.resolve().is_relative_to(original) or not dest.resolve().is_relative_to(source.resolve()):
                raise ValueError('Source manifest path escapes tree')
            if src.is_symlink():
                raise ValueError('Unexpected source link')
            data = src.read_bytes()
            if hashlib.sha256(data).hexdigest() != digest:
                raise ValueError('r5 prepared source changed: ' + name)
            dest.parent.mkdir(parents=True, exist_ok=True)
            with dest.open('xb') as stream:
                stream.write(data)
            if index % 10000 == 0:
                print('Source files verified:', index, flush=True)
        capcom.apply_source(source)
        source_hashes = reference.tree_hashes(source)
        binary = reference.run_build(source, work / 'build', msys, jobs)
    reference.verify_devices(work / 'build')
    runtime = work / 'runtime'
    runtime.mkdir()
    dlls = reference.upstream.stage_windows(binary, msys, runtime)
    staged = runtime / binary.name
    checks = reference.smoke_checks(staged, 'z62')
    if capcom.identity() != expected:
        raise ValueError('CAPCOM sources changed during build')
    common = {'binary': str(staged), 'binary_sha256': reference.upstream.digest(staged),
              'builder_sha256': reference.upstream.digest(Path(__file__)), 'capcom_device': expected}
    for name in ('reference', 'functional', 'transaction'):
        manifest = json.loads((old_root / (name + '-build-manifest.json')).read_text(encoding='utf-8'))
        manifest.update(common)
        if name == 'reference':
            manifest.update(source=str(source), build=str(work/'build'), runtime=str(runtime),
                prepared_source_file_sha256=source_hashes, runtime_dll_sha256=dlls,
                binary_bytes=staged.stat().st_size, checks=checks, jobs=jobs,
                inherited_from=str(old_root), firmware_run=False)
        else:
            key = 'generated_' + name + '_sha256'
            manifest[key] = {n: source_hashes['hw/arm/' + n] for n in manifest[key]}
        with (work / (name + '-build-manifest.json')).open('x', encoding='utf-8') as stream:
            json.dump(manifest, stream, indent=2)
    manifest = {**common, 'schema': 1, 'version': capcom.VERSION,
                'packaging_recovery': finish_staging,
                'source_board_sha256': source_hashes['hw/arm/nikon-z72.c'],
                'source_header_sha256': source_hashes['hw/arm/' + capcom.HEADER.name],
                'baseline_source_files_verified': len(hashes), 'checks': checks}
    (work / 'capcom-build-manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--jobs', type=int, default=12)
    parser.add_argument('--finish-staging', action='store_true')
    args = parser.parse_args()
    if not 1 <= args.jobs <= 32:
        parser.error('jobs must be 1..32')
    print(json.dumps(build(args.jobs, args.finish_staging), indent=2))
