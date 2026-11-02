"""Build an independent r8 snapshot from verified r7, preserving all old kernels."""
import argparse
import hashlib
import json
from pathlib import Path

import build_reference_qemu as reference
from build_z62_raw_stream import copy_verified_source
import run_z62_raw_stream as parent
import z62_finite_stats_device as device


def preserve_interrupted_copies(original, source, work, hashes):
    """Preserve only provable truncated-prefix build copies; reject other changes."""
    saved = []
    for name, expected in hashes.items():
        target, upstream = source/name, original/name
        if not target.exists():
            continue
        if not target.resolve().is_relative_to(source.resolve()) or target.is_symlink():
            raise ValueError('Unexpected recovery target')
        existing = target.read_bytes()
        if hashlib.sha256(existing).hexdigest() == expected:
            continue
        data = upstream.read_bytes()
        if hashlib.sha256(data).hexdigest() != expected or len(existing) >= len(data) or not data.startswith(existing):
            raise ValueError('Changed file is not a provable interrupted prefix: '+name)
        preserved = work/'interrupted-copy'/name
        if not preserved.resolve().is_relative_to(work.resolve()) or preserved.exists():
            raise ValueError('Unsafe or existing interrupted-copy destination')
        preserved.parent.mkdir(parents=True, exist_ok=True)
        target.rename(preserved)
        saved.append({'path':name, 'bytes':len(existing), 'expected_bytes':len(data),
                      'sha256':hashlib.sha256(existing).hexdigest(), 'expected_sha256':expected})
    with (work/'source-copy-recovery.json').open('x', encoding='utf-8') as handle:
        json.dump({'preserved_incomplete_files':saved, 'deleted_files':False}, handle, indent=2)
    print('Preserved incomplete generated copies:',len(saved),flush=True)


def build(jobs, resume_copy=False, repair_copy=False):
    prior = parent.verify_build(parent.DEFAULT_QEMU)
    parent_root = parent.DEFAULT_QEMU.parent.parent
    old = json.loads((parent_root/'reference-build-manifest.json').read_text(encoding='utf-8'))
    if resume_copy:
        work = device.WORK.absolute()
        for part in (work, *work.parents):
            if part.is_symlink() or (hasattr(part, 'is_junction') and part.is_junction()):
                raise ValueError('Linked recovery workspace')
        if not {p.name for p in work.iterdir()} <= {reference.MARKER, 'source', 'interrupted-copy', 'source-copy-recovery.json'}:
            raise ValueError('Only a pre-adapter source copy can resume')
        if json.loads((work/reference.MARKER).read_text()) != reference.identity('z62', True):
            raise ValueError('Recovery marker mismatch')
        work = work.resolve()
    else:
        work = reference.guard_workspace(device.WORK, 'z62', updates=True)
    identity = device.identity()
    if not resume_copy:
        work.mkdir(parents=True, exist_ok=False)
        (work/reference.MARKER).write_text(json.dumps(reference.identity('z62', True)), encoding='utf-8')
    source = work/'source/qemu-10.2.4'
    print('Preparing verified r7 snapshot', flush=True)
    if resume_copy:
        for path in source.rglob('*'):
            if path.is_file() and path.relative_to(source).as_posix() not in old['prepared_source_file_sha256']:
                raise ValueError('Unknown file in source-copy workspace: '+str(path))
    if repair_copy:
        preserve_interrupted_copies(Path(old['source']), source, work, old['prepared_source_file_sha256'])
    copy_verified_source(Path(old['source']), source, old['prepared_source_file_sha256'], resume=resume_copy)
    device.apply_source(source)
    hashes = dict(old['prepared_source_file_sha256'])
    changed = list(device.INPUTS) + [p.name for p in device.HEADERS]
    for name in changed:
        hashes['hw/arm/'+name] = reference.upstream.digest(source/'hw/arm'/name)
    (work/'prepared-finite-source.json').write_text(json.dumps({
        'finite_stats_device': identity, 'source_hashes': hashes,
        'parent_binary_sha256': prior['binary_sha256'], 'complete_build': False}, indent=2), encoding='utf-8')
    msys = Path(old['msys2_dir'])
    binary = reference.run_build(source, work/'build', msys, jobs)
    reference.verify_devices(work/'build')
    runtime = work/'runtime'
    runtime.mkdir()
    dlls = reference.upstream.stage_windows(binary, msys, runtime)
    staged = runtime/binary.name
    checks = reference.smoke_checks(staged, 'z62')
    if identity != device.identity():
        raise ValueError('Finite stats source changed during build')
    common = {'binary': str(staged), 'binary_sha256': reference.upstream.digest(staged),
        'builder_sha256': reference.upstream.digest(Path(__file__)), 'finite_stats_device': identity}
    for name in ('reference', 'functional', 'transaction', 'capcom', 'raw-stream'):
        previous = parent_root/(name+'-build-manifest.json')
        record = json.loads(previous.read_text(encoding='utf-8'))
        record.update(common)
        record['parent_manifest_sha256'] = reference.upstream.digest(previous)
        if name == 'reference':
            record.update(source=str(source), build=str(work/'build'), runtime=str(runtime),
                prepared_source_file_sha256=hashes, runtime_dll_sha256=dlls,
                binary_bytes=staged.stat().st_size, checks=checks, jobs=jobs,
                inherited_from=str(parent_root), firmware_run=False)
        elif name in ('functional', 'transaction'):
            key = 'generated_'+name+'_sha256'
            record['base_'+key] = record[key]
            record[key] = {n: hashes['hw/arm/'+n] for n in record[key]}
        else:
            record['base_source_board_sha256'] = record['source_board_sha256']
            record['source_board_sha256'] = hashes['hw/arm/nikon-z72.c']
        with (work/(name+'-build-manifest.json')).open('x', encoding='utf-8') as handle:
            json.dump(record, handle, indent=2)
    manifest = {**common, 'schema': 1, 'version': device.VERSION, 'checks': checks,
        'parent_binary_sha256': prior['binary_sha256'],
        'generated_source_sha256': {name: hashes['hw/arm/'+name] for name in changed}}
    with (work/'finite-stats-build-manifest.json').open('x', encoding='utf-8') as handle:
        json.dump(manifest, handle, indent=2)
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--jobs', type=int, default=12)
    parser.add_argument('--resume-copy', action='store_true')
    parser.add_argument('--repair-interrupted-copy', action='store_true')
    args = parser.parse_args()
    if not 1 <= args.jobs <= 32:
        parser.error('jobs must be 1..32')
    if args.repair_interrupted_copy and not args.resume_copy:
        parser.error('repair-interrupted-copy requires resume-copy')
    print(json.dumps(build(args.jobs, args.resume_copy, args.repair_interrupted_copy), indent=2))
