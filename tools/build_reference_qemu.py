"""Build pinned donor QEMU on native Windows; never run firmware.

Usage: python tools/build_reference_qemu.py z62 --msys2-dir D:/msys64 --jobs 4
--work-dir selects a NEW profile workspace (default .build/<profile>-reference),
not a shared build root. Existing/failed workspaces are never resumed or replaced.
Offline prerequisite: .build/downloads/qemu-10.2.4.tar.xz from build_qemu.py.
Dependencies must already be installed in the selected MSYS2 UCRT64 toolchain.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import types

import build_qemu as upstream
import reference_updates

ROOT = Path(__file__).resolve().parents[1]
COMMITS = {'z72': 'f6b80ec650116a6b0117d31f9ea112b05bb7f52a',
           'z62': '4f4389944fc339d107f22f5f7ca3f90cc34b78de'}
MACHINES = {profile: f'nikon-{profile}-dual-lab' for profile in COMMITS}
CONFIGURE = [*upstream.CONFIGURE, '--enable-pixman']
MARKER = '.reference-source.json'
CONVERSION_MARKER = 'GENERATED-TREE-CONVERTED-TO-Z62.txt'
OLD = b'object_property_add_uint64_ptr(obj, "frame-count", &s->frame_count,'
NEW = OLD.replace(b'uint64_ptr', b'uint32_ptr')
COMPATIBILITY = ('nikon-z72.c: frame-count read-only host QOM registration '
                 'uint64_ptr -> uint32_ptr; uint32 counter, guest and CPU unchanged')


def identity(profile, updates=False):
    result = {'schema': 1, 'profile': profile, 'donor_commit': COMMITS[profile],
              'qemu_version': upstream.QEMU_VERSION,
              'upstream_archive_sha256': upstream.ARCHIVE_SHA256,
              'configure': CONFIGURE, 'compatibility_changes': [COMPATIBILITY]}
    if updates:
        result['reference_updates'] = reference_updates.identity()
    return result


def guard_workspace(work, profile, updates=False):
    """Fail closed: even a matching previous build may have a running runtime."""
    work = Path(work).absolute()
    for part in (work, *work.parents):
        if part.is_symlink() or (hasattr(part, 'is_junction') and part.is_junction()):
            raise ValueError('Linked work directory is unsafe; choose a new --work-dir')
        if (part / CONVERSION_MARKER).exists():
            raise ValueError('Converted Z72 generated tree is protected; choose a new --work-dir')
        marker = part / MARKER
        if marker.exists():
            try:
                actual = json.loads(marker.read_text(encoding='utf-8'))
            except (ValueError, OSError) as exc:
                raise ValueError('Invalid source marker; choose a new --work-dir') from exc
            if actual != identity(profile, updates):
                raise ValueError('Source/profile marker mismatch; choose a new --work-dir')
            raise ValueError('Existing reference workspace is protected; choose a new --work-dir')
    work = work.resolve()
    for other in COMMITS:
        protected = (ROOT / '.build' / f'{other}-reference').resolve()
        if work != protected and work.is_relative_to(protected):
            raise ValueError('Do not nest inside an existing profile tree; choose a new --work-dir')
    if work.exists() and (not work.is_dir() or any(work.iterdir())):
        raise ValueError('Existing source/build/runtime or unknown provenance; choose a new --work-dir')
    return work


def verify_repository(profile):
    repo = ROOT / 'third_party' / f'{profile}-qemu'
    actual = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip()
    if actual != COMMITS[profile]:
        raise ValueError('Reference donor commit differs from pinned version: ' + profile)
    # HEAD comparison covers both staged and unstaged tracked changes, not untracked helpers.
    try:
        subprocess.run(['git', '-C', str(repo), 'diff', '--quiet', 'HEAD', '--'], check=True)
    except subprocess.CalledProcessError as exc:
        raise ValueError('Reference source contains tracked changes or git diff failed: ' + profile) from exc
    return repo


def snapshot_donor(repo, destination):
    """Execute only copied tracked source, never untracked helpers or cached pyc."""
    names = subprocess.check_output(
        ['git', '-C', str(repo), 'ls-files', '-z', '--', 'qemu']).decode('utf-8').split('\0')
    hashes = {}
    destination.mkdir()
    for name in filter(None, names):
        source, target = repo / name, destination / name
        if (source.is_symlink() or not source.is_file() or
                not target.resolve().is_relative_to(destination.resolve())):
            raise ValueError('Unsafe donor source entry: ' + name)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        hashes[name] = upstream.digest(target)
    if 'qemu/prepare_source.py' not in hashes or 'qemu/nikon-z72.c' not in hashes:
        raise ValueError('Missing tracked donor preparation interface')
    return hashes


def load_prepare(path):
    module = types.ModuleType('reference_prepare')
    module.__file__ = str(path)
    exec(compile(path.read_bytes(), str(path), 'exec'), module.__dict__)
    if not callable(getattr(module, 'prepare', None)) or not callable(getattr(module, 'prepare_screendump', None)):
        raise ValueError('Expected donor prepare(source) and prepare_screendump(source)')
    return module


def compatible_board(original):
    """Return the sole permitted host fix, preserving every other source byte."""
    declaration = rb'(?m)^    uint32_t frame_count;\r?$'
    registration = re.escape(OLD) + rb'\r?\n +OBJ_PROP_FLAG_READ\);'
    if (len(re.findall(declaration, original)) != 1 or original.count(OLD) != 1 or
            original.count(NEW) != 0 or len(re.findall(registration, original)) != 1):
        raise ValueError('Unexpected uint32 frame_count/read-only registration; refusing compatibility fix')
    return original.replace(OLD, NEW, 1)


def prepare_source(source, donor):
    helper = load_prepare(donor / 'qemu/prepare_source.py')
    helper.prepare(source)
    helper.prepare_screendump(source)
    board = source / 'hw/arm/nikon-z72.c'
    original = (donor / 'qemu/nikon-z72.c').read_bytes()
    if board.read_bytes() != original:
        raise ValueError('Donor board changed unexpectedly during preparation')
    expected = compatible_board(original)
    board.write_bytes(expected)
    for path in sorted((donor / 'qemu').iterdir()):
        if path.suffix not in ('.c', '.h'):
            continue
        target = source / 'hw/arm' / path.name
        wanted = expected if path.name == board.name else path.read_bytes()
        if not target.is_file() or target.read_bytes() != wanted:
            raise ValueError('Unexpected donor C/header change: ' + path.name)
    kconfig = (source / 'hw/arm/Kconfig').read_text(encoding='utf-8')
    sd = (source / 'hw/sd/Kconfig').read_text(encoding='utf-8')
    if ('    select SDHCI' not in kconfig.split('config NIKON_Z72_LAB', 1)[-1] or
            'config SDHCI\n    bool\n    select SD' not in sd):
        raise ValueError('Expected donor SDHCI -> upstream SD dependency')


def tree_hashes(root):
    hashes = {}
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            raise ValueError('Unexpected source link: ' + str(path))
        if path.is_file():
            hashes[path.relative_to(root).as_posix()] = upstream.digest(path)
    return hashes


def run_build(source, build, msys, jobs):
    # Reuse the tested Unicode-path/WINDRES/temp-file adaptations without leaking
    # configuration changes into callers that import the primary builder.
    previous = upstream.CONFIGURE
    try:
        upstream.CONFIGURE = list(CONFIGURE)
        return upstream.run_build(source, build, msys, jobs)
    finally:
        upstream.CONFIGURE = previous


def verify_devices(build):
    devices = (build / 'arm-softmmu-config-devices.h').read_text(encoding='utf-8')
    for option in ('CONFIG_SD', 'CONFIG_SDHCI', 'CONFIG_NIKON_Z72_LAB'):
        if not re.search(r'^#define ' + option + r' 1$', devices, re.MULTILINE):
            raise ValueError('Missing generated device option: ' + option)


def smoke_checks(binary, profile):
    """Only help/version commands; no firmware, machine realization or guest run."""
    env = dict(os.environ, PATH=str(Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'System32'))
    commands = {'version': ['--version'], 'machines': ['-M', 'help'],
                'machine_properties': ['-M', MACHINES[profile] + ',help']}
    if profile == 'z62':
        commands['sd_device_properties'] = ['-device', 'sd-card,help']
    checks = {}
    for name, args in commands.items():
        result = subprocess.run([str(binary), *args], cwd=binary.parent, env=env,
                                capture_output=True, check=True, timeout=60)
        checks[name] = (result.stdout + result.stderr).decode('utf-8', errors='replace')
    if upstream.QEMU_VERSION not in checks['version'] or MACHINES[profile] not in checks['machines']:
        raise ValueError('Staged QEMU version/machine does not match profile')
    if MACHINES[profile] + '-machine options:' not in checks['machine_properties']:
        raise ValueError('Missing staged machine property help')
    return checks


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('profile', choices=COMMITS)
    parser.add_argument('--msys2-dir', type=Path, required=True)
    parser.add_argument('--work-dir', type=Path, help='new profile workspace, not a shared parent')
    parser.add_argument('--jobs', type=int, default=4)
    parser.add_argument('--z62-updates', action='store_true',
                        help='Build opt-in versioned shoulder/input-trace reference updates')
    args = parser.parse_args(argv)
    if args.z62_updates and args.profile != 'z62':
        parser.error('--z62-updates requires z62')
    if not 1 <= args.jobs <= 32:
        parser.error('--jobs must be 1..32')
    args.work_dir = args.work_dir or ROOT / '.build' / f'{args.profile}-reference'
    return args


def build_reference(args):
    # All non-mutating guards precede creation, extraction or execution of donors.
    work = guard_workspace(args.work_dir, args.profile, args.z62_updates)
    if sys.platform != 'win32':
        raise ValueError('Reference builder requires native Windows Python and MSYS2 UCRT64')
    msys = args.msys2_dir.resolve()
    for name in ('usr/bin/bash.exe', 'ucrt64/bin/gcc.exe', 'ucrt64/bin/objdump.exe'):
        if not (msys / name).is_file():
            raise ValueError('Missing installed MSYS2 UCRT64 tool: ' + name)
    repo = verify_repository(args.profile)
    archive = ROOT / '.build/downloads' / f'qemu-{upstream.QEMU_VERSION}.tar.xz'
    if not archive.is_file():
        raise ValueError('Offline build requires cached upstream archive: ' + str(archive))
    if upstream.digest(archive) != upstream.ARCHIVE_SHA256:
        raise ValueError('Upstream QEMU SHA-256 mismatch')
    work.mkdir(parents=True, exist_ok=True)
    # Exclusive claim also prevents two builders from sharing an initially empty directory.
    with (work / MARKER).open('x', encoding='utf-8') as handle:
        json.dump(identity(args.profile, args.z62_updates), handle, indent=2)
        handle.write('\n')
    donor = work / 'donor'
    donor_hashes = snapshot_donor(repo, donor)
    verify_repository(args.profile)
    source = upstream.unpack(archive, work / 'source')
    if (source / '.z6ii-verified-extraction').read_text().strip() != upstream.ARCHIVE_SHA256:
        raise ValueError('Unexpected extracted upstream source marker; choose a new --work-dir')
    prepare_source(source, donor)
    if args.z62_updates:
        reference_updates.apply_source(source)
    source_hashes = tree_hashes(source)
    binary = run_build(source, work / 'build', msys, args.jobs)
    verify_devices(work / 'build')
    # Never copy into any pre-existing runtime, even if it appears to be unused.
    runtime = work / 'runtime'
    runtime.mkdir(exist_ok=False)
    dlls = upstream.stage_windows(binary, msys, runtime)
    staged = runtime / binary.name
    checks = smoke_checks(staged, args.profile)
    verify_repository(args.profile)
    manifest = {**identity(args.profile, args.z62_updates), 'source': str(source), 'build': str(work / 'build'),
                'runtime': str(runtime), 'binary': str(staged), 'jobs': args.jobs,
                'binary_sha256': upstream.digest(staged), 'binary_bytes': staged.stat().st_size,
                'runtime_dll_sha256': dlls, 'donor_file_sha256': donor_hashes,
                'prepared_source_file_sha256': source_hashes,
                'builder_sha256': upstream.digest(Path(__file__)),
                'upstream_builder_sha256': upstream.digest(ROOT / 'tools/build_qemu.py'),
                'msys2_dir': str(msys), 'checks': checks,
                'donor_preparation': ['prepare(source)', 'prepare_screendump(source)'],
                'sd_dependencies': 'donor selects SDHCI; upstream selects SD; generated values verified',
                'firmware_run': False, 'guest_patched': False, 'cpu_patched': False}
    with (work / 'reference-build-manifest.json').open('x', encoding='utf-8') as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)
        handle.write('\n')
    return manifest


def main(argv=None):
    args = parse_args(argv)
    try:
        manifest = build_reference(args)
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        raise SystemExit(str(exc)) from exc
    print('Built reference only (no firmware run): ' + manifest['binary'], flush=True)
    print('Manifest: ' + str(args.work_dir / 'reference-build-manifest.json'), flush=True)


if __name__ == '__main__':
    main()
