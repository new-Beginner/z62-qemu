# SPDX-License-Identifier: GPL-2.0-or-later
"""Independent native Windows r5 build: donor -> r1 -> unchanged r4 -> r5."""
import argparse
import json
from pathlib import Path
import sys
import build_reference_qemu as reference
import reference_updates
import z62_functional_device as functional
import z62_transaction_device as transaction

ROOT = reference.ROOT
WORK = ROOT / '.build' / ('z62-transaction-' + transaction.VERSION)
R4 = ROOT / '.build/z62-functional-2026.10.28-r4'


def build(args):
    work = reference.guard_workspace(WORK, 'z62', updates=True)
    if sys.platform != 'win32':
        raise ValueError('Native Windows Python and MSYS2 UCRT64 required')
    old = json.loads((R4 / 'functional-build-manifest.json').read_text(encoding='utf-8'))
    if old['functional_device'] != functional.identity():
        raise ValueError('r4 source identity mismatch')
    msys = (args.msys2_dir or Path(old['msys2_dir'])).resolve()
    for name in ('usr/bin/bash.exe', 'ucrt64/bin/gcc.exe', 'ucrt64/bin/objdump.exe'):
        if not (msys / name).is_file():
            raise ValueError('Missing toolchain file: ' + name)
    repo = reference.verify_repository('z62')
    upstream = reference.upstream
    archive = ROOT / '.build/downloads' / f'qemu-{upstream.QEMU_VERSION}.tar.xz'
    if not archive.is_file() or upstream.digest(archive) != upstream.ARCHIVE_SHA256:
        raise ValueError('Invalid cached QEMU archive')
    identities = (reference_updates.identity(), functional.identity(), transaction.identity())
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
    r4_generated = {name: upstream.digest(source / 'hw/arm' / name)
                    for name in (*functional.INPUTS, functional.HEADER.name)}
    if r4_generated != old['generated_functional_sha256']:
        raise ValueError('Prepared r4 source differs from original r4 manifest')
    transaction.apply_source(source)
    source_hashes = reference.tree_hashes(source)
    binary = reference.run_build(source, work / 'build', msys, args.jobs)
    reference.verify_devices(work / 'build')
    runtime = work / 'runtime'
    runtime.mkdir(exist_ok=False)
    dlls = upstream.stage_windows(binary, msys, runtime)
    staged = runtime / binary.name
    checks = reference.smoke_checks(staged, 'z62')
    reference.verify_repository('z62')
    if identities != (reference_updates.identity(), functional.identity(), transaction.identity()):
        raise ValueError('Source adapters changed during build')
    manifest = {**reference.identity('z62', True),
                'functional_device': identities[1], 'transaction_device': identities[2],
                'source': str(source), 'build': str(work / 'build'), 'runtime': str(runtime),
                'binary': str(staged), 'binary_sha256': upstream.digest(staged),
                'binary_bytes': staged.stat().st_size, 'runtime_dll_sha256': dlls,
                'donor_file_sha256': donor_hashes, 'prepared_source_file_sha256': source_hashes,
                'builder_sha256': upstream.digest(Path(__file__)), 'jobs': args.jobs,
                'msys2_dir': str(msys), 'checks': checks,
                'firmware_run': False, 'guest_patched': False, 'cpu_patched': False}
    common = {key: manifest[key] for key in ('binary', 'binary_sha256', 'reference_updates',
              'functional_device', 'transaction_device', 'builder_sha256', 'msys2_dir', 'donor_commit')}
    functional_manifest = {**common, 'schema': 1, 'version': functional.VERSION,
        'base_generated_functional_sha256': r4_generated,
        'generated_functional_sha256': {name: source_hashes['hw/arm/' + name] for name in r4_generated}}
    transaction_manifest = {**common, 'schema': 1, 'version': transaction.VERSION,
        'base_generated_functional_sha256': r4_generated,
        'generated_transaction_sha256': {name: source_hashes['hw/arm/' + name]
                                        for name in (*transaction.INPUTS, transaction.HEADER.name)}}
    for name, data in (('reference', manifest), ('functional', functional_manifest),
                       ('transaction', transaction_manifest)):
        with (work / (name + '-build-manifest.json')).open('x', encoding='utf-8') as handle:
            json.dump(data, handle, indent=2)
            handle.write('\n')
    return transaction_manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--msys2-dir', type=Path)
    parser.add_argument('--jobs', type=int, default=12)
    args = parser.parse_args()
    if not 1 <= args.jobs <= 32:
        parser.error('--jobs must be 1..32')
    print(json.dumps(build(args), indent=2), flush=True)


if __name__ == '__main__':
    main()
