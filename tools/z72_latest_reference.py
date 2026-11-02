"""Build/run Z72 upstream 4a7bed3 without changing the older reference pins.

Local integration 2026.10.28-r1; experimental parameters, no camera access.
The dedicated upstream worktree must already be fetched and checked out.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys

import build_reference_qemu as builder
import run_reference_console as console

VERSION = '2026.10.28-r1'
COMMIT = '4a7bed36b6e747f58d5ab25f31b06a31fa7c6ec2'
ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = ROOT / '.build/z72-latest-4a7bed3-upstream'
WORK = ROOT / ('.build/z72-latest-' + VERSION)


def verify_repository(profile):
    if profile != 'z72':
        raise ValueError('This dedicated integration supports Z72 only')
    actual = subprocess.check_output(
        ['git', '-C', str(REPOSITORY), 'rev-parse', 'HEAD'], text=True).strip()
    if actual != COMMIT:
        raise ValueError('Latest Z72 worktree does not match the recorded commit')
    subprocess.run(['git', '-C', str(REPOSITORY), 'diff', '--quiet', 'HEAD', '--'], check=True)
    return REPOSITORY


def configure():
    # Process-local configuration only: old scripts, pins and runtimes stay intact.
    verify_repository('z72')
    builder.COMMITS = {**builder.COMMITS, 'z72': COMMIT}
    console.COMMITS = {**console.COMMITS, 'z72': COMMIT}
    builder.verify_repository = verify_repository
    console.verify_repository = verify_repository
    console.HOST_VERSION = VERSION


def verify_binary():
    binary = WORK / 'runtime/qemu-system-arm.exe'
    manifest = json.loads((WORK / 'reference-build-manifest.json').read_text(encoding='utf-8'))
    if (manifest.get('profile') != 'z72' or manifest.get('donor_commit') != COMMIT or
            manifest.get('binary_sha256') != builder.upstream.digest(binary)):
        raise ValueError('QEMU does not match the latest Z72 build manifest')
    return binary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('build', 'run'))
    parser.add_argument('--version', action='version', version=VERSION)
    parser.add_argument('--msys2-dir', type=Path)
    parser.add_argument('--jobs', type=int, default=12)
    parser.add_argument('--port', type=int, default=8666)
    parser.add_argument('--no-auto-menu', action='store_true')
    args = parser.parse_args()
    if not 1 <= args.jobs <= 32 or not 1 <= args.port <= 65535:
        parser.error('jobs must be 1..32 and port must be 1..65535')
    configure()
    if args.action == 'build':
        if args.msys2_dir is None:
            parser.error('build requires --msys2-dir')
        build_args = builder.parse_args(['z72', '--msys2-dir', str(args.msys2_dir),
                                         '--work-dir', str(WORK), '--jobs', str(args.jobs)])
        manifest = builder.build_reference(build_args)
        print('Built Z72 ' + COMMIT + ': ' + manifest['binary'], flush=True)
    else:
        binary = verify_binary()
        print('Z72 upstream: ' + COMMIT, flush=True)
        sys.argv = [str(Path(console.__file__)), 'z72', '--qemu', str(binary), '--port', str(args.port)]
        if args.no_auto_menu:
            sys.argv.append('--no-auto-menu')
        console.main()


if __name__ == '__main__':
    main()
