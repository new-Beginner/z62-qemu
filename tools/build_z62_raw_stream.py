# SPDX-License-Identifier: GPL-2.0-or-later
"""Build isolated r7 from fully verified r6 source files; never overwrite r6."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import sys

import build_reference_qemu as reference
import run_z62_capcom as r6
import z62_raw_stream_device as stream


def comparison_path(path):
    """Normalize equivalent Win32/extended paths for containment, not file I/O.

    Python's non-strict Windows resolve can retain the extended prefix when
    another thread creates a parent while it resolves an absent child.
    Do not normalize device namespaces such as GLOBALROOT or drive-relative paths.
    """
    value = str(path)
    if value.startswith('\\\\?\\UNC\\'):
        return type(path)('\\\\'+value[8:])
    if value.startswith('\\\\?\\') and len(value) >= 7 and value[4].isalpha() and value[5:7] == ':\\':
        return type(path)(value[4:])
    return path


def copy_verified_source(original, destination, hashes, workers=6, resume=False):
    original = original.resolve(strict=True)
    destination = destination.absolute()
    for part in (destination, *destination.parents):
        if part.is_symlink() or (hasattr(part, 'is_junction') and part.is_junction()):
            raise ValueError('Linked destination is not a source snapshot')
    # Establish the canonical destination before worker threads create children.
    destination.mkdir(parents=True, exist_ok=True)
    destination = destination.resolve(strict=True)
    source_root, destination_root = comparison_path(original), comparison_path(destination)
    def copy(entry):
        name, expected = entry
        src, dest = original / name, destination / name
        resolved_source, resolved_target = comparison_path(src.resolve()), comparison_path(dest.resolve())
        if not resolved_source.is_relative_to(source_root) or not resolved_target.is_relative_to(destination_root):
            raise ValueError(f'Source manifest escapes tree: {name}; source={str(resolved_source)!r}; '
                             f'target={str(resolved_target)!r}; roots={str(original)!r}, {str(destination)!r}')
        if src.is_symlink():
            raise ValueError('Unexpected source link')
        data = src.read_bytes()
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError('Source hash changed: ' + name)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if resume and dest.exists():
            if dest.is_symlink() or hashlib.sha256(dest.read_bytes()).hexdigest() != expected:
                raise ValueError('Existing partial source differs: ' + name)
            return name
        with dest.open('xb') as handle:
            handle.write(data)
        return name
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for count, _ in enumerate(pool.map(copy, hashes.items()), 1):
            if count % 10000 == 0:
                print('Verified source files:', count, flush=True)


def build(jobs, resume_copy=False):
    if sys.platform != 'win32':
        raise ValueError('Native Windows toolchain required')
    parent = r6.verify_build(r6.DEFAULT_QEMU)
    parent_root = r6.DEFAULT_QEMU.parent.parent
    old = json.loads((parent_root/'reference-build-manifest.json').read_text(encoding='utf-8'))
    if resume_copy:
        work = stream.WORK.absolute()
        for part in (work, *work.parents):
            if part.is_symlink() or (hasattr(part, 'is_junction') and part.is_junction()):
                raise ValueError('Linked recovery workspace')
        if {p.name for p in work.iterdir()} != {reference.MARKER, 'source'}:
            raise ValueError('Only a pre-adapter source-copy failure can resume')
        if json.loads((work/reference.MARKER).read_text()) != reference.identity('z62', True):
            raise ValueError('Recovery marker mismatch')
        work = work.resolve()
    else:
        work = reference.guard_workspace(stream.WORK, 'z62', updates=True)
    msys = Path(old['msys2_dir'])
    if not (msys/'ucrt64/bin/gcc.exe').is_file():
        raise ValueError('Recorded MSYS2 compiler missing')
    identity = stream.identity()
    if not resume_copy:
        work.mkdir(parents=True, exist_ok=False)
        (work/reference.MARKER).write_text(json.dumps(reference.identity('z62', True)), encoding='utf-8')
    source = work/'source/qemu-10.2.4'
    print('Preparing verified r6 source snapshot', flush=True)
    if resume_copy:
        for path in source.rglob('*'):
            if path.is_file() and path.relative_to(source).as_posix() not in old['prepared_source_file_sha256']:
                raise ValueError('Unknown file in partial source snapshot: ' + str(path))
    copy_verified_source(Path(old['source']), source, old['prepared_source_file_sha256'], resume=resume_copy)
    stream.apply_source(source)
    source_hashes = dict(old['prepared_source_file_sha256'])
    for name in ('nikon-z72.c', stream.HEADER.name):
        source_hashes['hw/arm/'+name] = reference.upstream.digest(source/'hw/arm'/name)
    # Persist the verified preparation before compiling, so failures have a
    # concrete source identity without implying a runnable release exists.
    preparation = {'stream_device': identity, 'parent_binary_sha256': parent['binary_sha256'],
                   'source_hashes': source_hashes, 'complete_build': False}
    (work/'prepared-stream-source.json').write_text(json.dumps(preparation, indent=2), encoding='utf-8')
    binary = reference.run_build(source, work/'build', msys, jobs)
    reference.verify_devices(work/'build')
    runtime = work/'runtime'
    runtime.mkdir()
    dlls = reference.upstream.stage_windows(binary, msys, runtime)
    staged = runtime/binary.name
    checks = reference.smoke_checks(staged, 'z62')
    if identity != stream.identity():
        raise ValueError('RAW stream source changed during build')
    common = {'binary': str(staged), 'binary_sha256': reference.upstream.digest(staged),
              'builder_sha256': reference.upstream.digest(Path(__file__)), 'raw_stream_device': identity}
    for name in ('reference', 'functional', 'transaction', 'capcom'):
        previous = parent_root/(name+'-build-manifest.json')
        record = json.loads(previous.read_text(encoding='utf-8'))
        record.update(common)
        record['parent_manifest_sha256'] = reference.upstream.digest(previous)
        if name == 'reference':
            record.update(source=str(source), build=str(work/'build'), runtime=str(runtime),
                prepared_source_file_sha256=source_hashes, runtime_dll_sha256=dlls,
                binary_bytes=staged.stat().st_size, checks=checks, jobs=jobs,
                inherited_from=str(parent_root), firmware_run=False)
        elif name in ('functional', 'transaction'):
            key = 'generated_'+name+'_sha256'
            record['base_'+key] = record[key]
            record[key] = {n: source_hashes['hw/arm/'+n] for n in record[key]}
        else:
            record['base_source_board_sha256'] = record['source_board_sha256']
            record['source_board_sha256'] = source_hashes['hw/arm/nikon-z72.c']
        with (work/(name+'-build-manifest.json')).open('x', encoding='utf-8') as handle:
            json.dump(record, handle, indent=2)
    manifest = {**common, 'schema': 1, 'version': stream.VERSION, 'checks': checks,
                'parent_binary_sha256': parent['binary_sha256'],
                'source_board_sha256': source_hashes['hw/arm/nikon-z72.c'],
                'source_header_sha256': source_hashes['hw/arm/'+stream.HEADER.name]}
    with (work/'raw-stream-build-manifest.json').open('x', encoding='utf-8') as handle:
        json.dump(manifest, handle, indent=2)
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--jobs', type=int, default=12)
    parser.add_argument('--resume-copy', action='store_true')
    args = parser.parse_args()
    if not 1 <= args.jobs <= 32:
        parser.error('jobs must be 1..32')
    print(json.dumps(build(args.jobs, args.resume_copy), indent=2))
