"""Build the Z6II QEMU lab from pinned upstream source; no firmware bundled.

Windows: python tools/build_qemu.py --msys-root <MSYS2 root> --jobs 4
Linux:   python tools/build_qemu.py --jobs 4
Dependencies are supplied by the selected toolchain, never silently installed.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import subprocess
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
LAB_VERSION = '0.4.0'
QEMU_VERSION = '10.2.4'
ARCHIVE_SHA256 = '821b545b92f165e57dddccac5077d76d4d436a226595b8813ad59306bbfd0746'
CONFIGURE = ['--target-list=arm-softmmu', '--without-default-devices',
             '--without-default-features', '--enable-tcg', '--enable-fdt', '--disable-docs',
             '--disable-tools', '--disable-user', '--disable-werror',
             '--disable-guest-agent', '--disable-rust', '--disable-debug-info',
             '--disable-download']


def digest(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def archive_filter(member, destination):
    # Archive is SHA-256 pinned. Reject traversal, Windows drive syntax and ALL
    # links. This avoids Windows symlink privileges and slow per-member realpath.
    name = PurePosixPath(member.name)
    if (name.is_absolute() or '..' in name.parts or ':' in member.name or
            chr(92) in member.name or not name.parts or
            name.parts[0] != f'qemu-{QEMU_VERSION}'):
        raise ValueError(f'Unsafe upstream archive path: {member.name}')
    if member.issym() or member.islnk():
        return None  # EDK2 links are not used by the minimal ARM build.
    if not member.isdir() and not member.isfile():
        raise ValueError(f'Unexpected archive member type: {member.name}')
    return member


def unpack(archive, destination):
    if digest(archive) != ARCHIVE_SHA256:
        raise ValueError('Upstream QEMU SHA-256 mismatch')
    source = destination / f'qemu-{QEMU_VERSION}'
    marker = source / '.z6ii-verified-extraction'
    if not marker.exists():
        destination.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive, 'r|xz') as t:
            t.extractall(destination, filter=archive_filter)
        marker.write_text(ARCHIVE_SHA256 + '\n', encoding='ascii')
    elif marker.read_text().strip() != ARCHIVE_SHA256:
        raise ValueError('Unexpected source marker; choose a clean source directory')
    return source


def prepare_source(source):
    if (source / 'VERSION').read_text().strip() != QEMU_VERSION:
        raise ValueError('Expected pinned QEMU 10.2.4 source')
    changes = {
        'hw/arm/meson.build': "arm_ss.add(when: 'CONFIG_NIKON_Z6II', if_true: files('nikon-z6ii.c'))\n",
        'hw/arm/Kconfig': '\nconfig NIKON_Z6II\n    bool\n    depends on TCG && ARM\n    select GENERIC_LOADER\n    select A15MPCORE\n',
        'configs/devices/arm-softmmu/default.mak': '\nCONFIG_NIKON_Z6II=y\n',
    }
    for name, addition in changes.items():
        path = source / name
        original = path.read_text(encoding='utf-8')
        if 'NIKON_Z6II' in original and addition.strip() not in original:
            raise ValueError(f'Conflicting Z6II integration: {path}')
        if addition.strip() not in original:
            path.write_text(original + addition, encoding='utf-8', newline='\n')
    shutil.copyfile(ROOT / 'qemu/nikon-z6ii.c', source / 'hw/arm/nikon-z6ii.c')
    shutil.copyfile(ROOT / 'qemu/nikon-z6ii-platform.h', source / 'hw/arm/nikon-z6ii-platform.h')


def msys_path(path):
    path = Path(path).resolve().as_posix()
    if len(path) < 3 or path[1:3] != ':/':
        raise ValueError('Windows MSYS build needs a local drive path')
    return '/' + path[0].lower() + path[2:]


def run_build(source, build, msys_root, jobs):
    build.mkdir(parents=True, exist_ok=True)
    if os.name == 'nt':
        if not msys_root or not (msys_root / 'ucrt64/bin/gcc.exe').is_file():
            raise ValueError('--msys-root must select an installed UCRT64 toolchain')
        bash = msys_root / 'usr/bin/bash.exe'
        env = dict(os.environ, MSYSTEM='UCRT64', CHERE_INVOKING='1',
                   PYTHONUTF8='1', PYTHONIOENCODING='utf-8', LANG='C.UTF-8', LC_ALL='C.UTF-8',
                   WINDRES=shlex.join(['windres', '--use-temp-file', '-I', Path(os.path.relpath(source, build)).as_posix()]),
                   PATH=str(msys_root / 'usr/bin') + ';' + os.environ.get('SystemRoot', 'C:/Windows') + '/System32')
        commands = ['export PATH=/ucrt64/bin:/usr/bin:/c/Windows/System32 TMP=/tmp TEMP=/tmp',
                    'cd ' + shlex.quote(msys_path(build))]
        # Reconfigure also refreshes the selected resource compiler/workarounds.
        commands.append(shlex.quote(msys_path(source / 'configure')) + ' ' + shlex.join(CONFIGURE))
        commands.append(f'ninja -j {jobs} qemu-system-arm.exe')
        subprocess.run([str(bash), '--noprofile', '--norc', '-c', ' && '.join(commands)],
                       env=env, check=True)
        return build / 'qemu-system-arm.exe'
    if not (build / 'build.ninja').is_file():
        subprocess.run([str(source / 'configure'), *CONFIGURE], cwd=build, check=True)
    subprocess.run(['ninja', '-j', str(jobs), 'qemu-system-arm'], cwd=build, check=True)
    return build / 'qemu-system-arm'


def stage_windows(binary, msys_root, destination):
    """Copy only transitively imported non-system DLLs, using native objdump."""
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copy2(binary, destination / binary.name)
    libdir = msys_root / 'ucrt64/bin'
    libraries = {p.name.lower(): p for p in libdir.glob('*.dll')}
    pending, copied = [binary], {}
    env = dict(os.environ, PATH=str(libdir) + ';' + os.environ.get('PATH', ''))
    while pending:
        item = pending.pop()
        # Native binutils may reject a Unicode argv path even though Windows
        # can set that same directory as cwd. Keep the inspected filename ASCII.
        output = subprocess.run([str(libdir / 'objdump.exe'), '-p', item.name], cwd=item.parent,
                                capture_output=True, text=True, errors='replace', env=env, check=True).stdout
        for name in re.findall(r'DLL Name:\s*(\S+)', output):
            key = name.lower()
            if key in libraries and key not in copied:
                original = libraries[key]
                shutil.copy2(original, destination / original.name)
                copied[key] = digest(original)
                pending.append(original)
            elif key not in libraries and not (key.startswith(('api-ms-', 'ext-ms-')) or
                    (Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'System32' / name).exists()):
                raise ValueError(f'Unresolved runtime DLL: {name}')
    license_source = msys_root / 'ucrt64/share/licenses'
    if license_source.exists():
        shutil.copytree(license_source, destination / 'dependency-licenses', dirs_exist_ok=True)
    return copied


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--msys-root', type=Path)
    parser.add_argument('--work-dir', type=Path, default=ROOT / '.build')
    parser.add_argument('--jobs', type=int, default=4)
    args = parser.parse_args()
    if not 1 <= args.jobs <= 32:
        parser.error('--jobs must be 1..32')
    work = args.work_dir.resolve()
    downloads = work / 'downloads'
    downloads.mkdir(parents=True, exist_ok=True)
    archive = downloads / f'qemu-{QEMU_VERSION}.tar.xz'
    if not archive.exists():
        print('Downloading pinned QEMU source', flush=True)
        with urllib.request.urlopen(f'https://download.qemu.org/qemu-{QEMU_VERSION}.tar.xz', timeout=60) as r:
            with archive.open('wb') as f:
                shutil.copyfileobj(r, f)
    print('Verifying/extracting upstream source', flush=True)
    source = unpack(archive, work / 'source')
    prepare_source(source)
    binary = run_build(source, work / 'qemu-build', args.msys_root, args.jobs)
    platform_name = 'windows-x64' if os.name == 'nt' else 'linux'
    destination = ROOT / 'dist' / f'z6ii-qemu-v{LAB_VERSION}-{platform_name}'
    destination.mkdir(parents=True, exist_ok=True)
    dependencies = stage_windows(binary, args.msys_root, destination) if os.name == 'nt' else {}
    if os.name != 'nt':
        shutil.copy2(binary, destination / binary.name)
    shutil.copy2(source / 'COPYING', destination / 'COPYING-QEMU')
    overlay = destination / 'source-overlay'
    overlay.mkdir(exist_ok=True)
    shutil.copy2(ROOT / 'qemu/nikon-z6ii.c', overlay / 'nikon-z6ii.c')
    shutil.copy2(ROOT / 'qemu/nikon-z6ii-platform.h', overlay / 'nikon-z6ii-platform.h')
    shutil.copy2(Path(__file__), overlay / 'build_qemu.py')
    (destination / 'tools').mkdir(exist_ok=True)
    shutil.copy2(ROOT / 'tools/run_qemu.py', destination / 'tools/run_qemu.py')
    shutil.copy2(ROOT / 'qemu/run-package.cmd', destination / 'run.cmd')
    shutil.copy2(ROOT / 'README-QEMU.md', destination / 'README-QEMU.md')
    shutil.copy2(ROOT / 'analysis/qemu-v0.3.0/boot-evidence.json', destination / 'boot-evidence.json')
    shutil.copy2(ROOT / 'analysis/qemu-v0.4.0/platform-evidence.json', destination / 'platform-evidence.json')
    manifest = {'lab_version': LAB_VERSION, 'qemu_version': QEMU_VERSION,
                'upstream_url': f'https://download.qemu.org/qemu-{QEMU_VERSION}.tar.xz',
                'upstream_archive_sha256': ARCHIVE_SHA256, 'machine': 'nikon-z6ii',
                'binary': binary.name, 'binary_sha256': digest(binary),
                'board_sha256': digest(ROOT / 'qemu/nikon-z6ii.c'),
                'platform_header_sha256': digest(ROOT / 'qemu/nikon-z6ii-platform.h'),
                'builder_sha256': digest(Path(__file__)), 'configure': CONFIGURE,
                'launcher_sha256': digest(ROOT / 'tools/run_qemu.py'),
                'runtime_dll_sha256': dependencies,
                'boot_configuration': '346 exact uint32 words; experimental synchronous command/status, W1C and readonly results; no guest patches',
                'reference_repository': 'https://github.com/JKWTCN/z72-qemu',
                'reference_commit': 'f6b80ec650116a6b0117d31f9ea112b05bb7f52a',
                'boot_evidence_sha256': digest(destination / 'boot-evidence.json'),
                'platform_evidence_sha256': digest(destination / 'platform-evidence.json'),
                'menu_supported': False, 'dual_chip_ipc_modeled': False}
    (destination / 'build-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    subprocess.run([str(destination / binary.name), '--version'], check=True)
    print('Built: ' + str(destination), flush=True)
    archive_path = Path(shutil.make_archive(str(destination), 'zip', destination.parent, destination.name))
    archive_path.with_suffix('.zip.sha256').write_text(
        digest(archive_path) + '  ' + archive_path.name + '\n', encoding='ascii', newline='\n')
    print('Package: ' + str(archive_path), flush=True)


if __name__ == '__main__':
    main()
