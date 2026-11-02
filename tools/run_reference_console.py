"""Run pinned donor consoles natively, with immutable firmware and ASCII paths.

This is a reference experiment, not the Z6II v0.4.0 release. Z62 synthetic
parameters require explicit opt-in and are NOT recovered factory calibration.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy
import shutil
import struct
import subprocess
import sys
import tempfile

from prepare_reference_firmware import ROOT, PROFILES
import reference_updates
from z62_capture_observation import PRESETS, install_preset

HOST_VERSION = '2026.10.28-r3'


def validate_sd_card(profile, path):
    """Accept regular raw image files only; never physical disk device paths."""
    if path is None:
        return None
    if profile != 'z62':
        raise ValueError('--sd-card is supported only for z62')
    path = Path(path).resolve()
    if not path.is_file():
        raise ValueError('SD image must be an existing regular file')
    # QEMU -drive uses commas as option separators. Reject rather than allowing
    # a filename to inject options (in particular snapshot=off).
    if ',' in str(path) or not str(path).isascii():
        raise ValueError('SD image requires an ASCII path without commas')
    if path.stat().st_size == 0 or path.stat().st_size % 512:
        raise ValueError('Raw SD image size must be a positive multiple of 512 bytes')
    return path
COMMITS = {'z72': 'f6b80ec650116a6b0117d31f9ea112b05bb7f52a',
           'z62': '4f4389944fc339d107f22f5f7ca3f90cc34b78de'}


def verify_repository(profile):
    repo = ROOT / 'third_party' / f'{profile}-qemu'
    actual = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip()
    if actual != COMMITS[profile]:
        raise ValueError('Reference commit differs from reviewed version')
    if subprocess.call(['git', '-C', str(repo), 'diff', '--quiet', 'HEAD', '--']) != 0:
        raise ValueError('Reference source contains tracked changes; review before executing')
    return repo


def copy_tracked_source(repo, destination):
    """Do not execute untracked helper files from a reference worktree."""
    names = subprocess.check_output(['git', '-C', str(repo), 'ls-files', '-z']).decode('utf-8').split('\0')
    destination.mkdir()
    for name in filter(None, names):
        source = repo / name
        target = destination / name
        if source.is_symlink() or not source.is_file() or not target.resolve().is_relative_to(destination.resolve()):
            raise ValueError('Unsafe reference source entry: ' + name)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)


def synthetic_parameters(destination):
    """Explicit candidate fixture, mostly zeros; never presented as a NOR dump."""
    primary, secondary, resource = bytearray(0x20000), bytearray(0xA0000), bytearray(0x180000)
    # Z72 public fixture values are candidates only for Z62, not calibration.
    struct.pack_into('<I', primary, 0xA420, 81)
    struct.pack_into('<3I', primary, 0xA124, 1120, 1120, 1120)
    primary[0xB4E4], primary[0xB4E8] = 70, 75
    # Z62 version check differs from Z72's 0xBE014 (documented in z62-port.md).
    resource[0xCE014:0xCE016] = b'\x15\0'
    destination.mkdir(exist_ok=False)
    groups = {}
    for name, data in zip(('group17.bin', 'group18.bin', 'group32.bin'), (primary, secondary, resource)):
        data[-4:] = b'ENDM'
        (destination / name).write_bytes(data)
        groups[name] = {'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    record = {'experimental': True, 'factory_calibration': False, 'nor_dump': False,
              'groups': groups, 'origin': 'Candidate based on public Z72 fixture plus Z62 resource-version offset',
              'limits': 'No sensor calibration, serial, resource body or real configuration recovered.'}
    (destination / 'parameters.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    return record


def stage(profile, qemu, parameters=None, experimental_parameters=False, updates=False):
    repo = verify_repository(profile)
    qemu = qemu.resolve()
    if not qemu.is_file():
        raise ValueError('Build the reference QEMU first: ' + str(qemu))
    if updates:
        if profile != 'z62':
            raise ValueError('Reference updates require z62')
        reference_updates.verify_binary(qemu)
    if profile == 'z62' and (parameters is None) == (not experimental_parameters):
        raise ValueError('Z62 requires exactly one of --parameters or --experimental-parameters')
    scratch = os.environ.get('PI_SCRATCH_DIR') or tempfile.gettempdir()
    if not str(scratch).isascii() or ',' in str(scratch):
        raise ValueError('Reference runtime requires an ASCII scratch directory without commas')
    work = Path(tempfile.mkdtemp(prefix=profile + '-reference-', dir=scratch))
    # Copy source only. No mutations in the pinned submodule worktree.
    copy_tracked_source(repo, work / 'source')
    if updates:
        reference_updates.apply_console(work / 'source')
    inputs = work / 'inputs'
    inputs.mkdir()
    files = {}
    for name, (filename, size, digest) in PROFILES[profile]['members'].items():
        source = ROOT / 'artifacts' / f'{profile}-reference-1.70' / filename
        data = source.read_bytes()
        if len(data) != size or hashlib.sha256(data).hexdigest() != digest:
            raise ValueError('Wrong complete firmware member: ' + name)
        target = inputs / filename
        target.write_bytes(data)
        files[filename] = {'size': size, 'sha256': digest}
    fixture = None
    if profile == 'z62':
        target = work / 'parameters'
        if experimental_parameters:
            fixture = synthetic_parameters(target)
        else:
            target.mkdir()
            for name, size in (('group17.bin', 0x20000), ('group18.bin', 0xA0000), ('group32.bin', 0x180000)):
                data = (parameters / name).read_bytes()
                if len(data) != size or data[-4:] != b'ENDM':
                    raise ValueError('Invalid supplied parameter group: ' + name)
                (target / name).write_bytes(data)
            fixture = {'experimental': None, 'factory_calibration': 'user-supplied, not independently verified'}
    record = {'profile': profile, 'reference_commit': COMMITS[profile],
              'qemu': str(qemu), 'qemu_sha256': hashlib.sha256(qemu.read_bytes()).hexdigest(),
              'inputs': files, 'parameters': fixture,
              'reference_updates': reference_updates.identity() if updates else None,
              'guest_patched': False, 'camera_accessed': False,
              'host_adaptation': 'ASCII staging, slash normalization and Windows NUL qtest log only',
              'work': str(work)}
    (work / 'session.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return work, record


def install_native_process_adapter(work):
    """Change host argument paths/log sink only; no guest register/memory writes."""
    original = subprocess.Popen

    class NativePopen(original):
        def __init__(self, command, *args, **kwargs):
            if isinstance(command, (list, tuple)) and 'qemu-system-arm' in str(command[0]):
                command = [str(part).replace('\\', '/') for part in command]
                if os.name == 'nt' and '-qtest-log' in command:
                    command[command.index('-qtest-log') + 1] = 'NUL'
                index = len(list(work.glob('effective-command-*.json')))
                (work / f'effective-command-{index}.json').write_text(
                    json.dumps(command, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            super().__init__(command, *args, **kwargs)

    subprocess.Popen = NativePopen
    return original


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('profile', choices=COMMITS)
    parser.add_argument('--version', action='version', version=HOST_VERSION)
    parser.add_argument('--sd-card', type=Path,
                        help='Z62 raw SD image; guest writes use a temporary snapshot, not the original')
    parser.add_argument('--qemu', type=Path)
    parser.add_argument('--port', type=int)
    parser.add_argument('--parameters', type=Path)
    parser.add_argument('--experimental-parameters', action='store_true')
    parser.add_argument('--no-auto-menu', action='store_true')
    parser.add_argument('--z62-updates', action='store_true')
    parser.add_argument('--sampling-source', action='store_true',
                        help='Opt-in experimental sample-ready source; no sensor pixels')
    parser.add_argument('--input-trace', action='store_true')
    parser.add_argument('--capture-preset', choices=PRESETS, default='baseline',
                        help='Explicit Z62 laboratory completion sources; not pixels or factory calibration')
    args = parser.parse_args()
    if args.capture_preset != 'baseline' and (args.profile != 'z62' or not args.z62_updates):
        parser.error('experimental capture presets require z62 --z62-updates')
    if (args.sampling_source or args.input_trace) and not args.z62_updates:
        parser.error('--sampling-source/--input-trace require --z62-updates')
    if args.z62_updates and args.profile != 'z62':
        parser.error('--z62-updates requires z62')
    if args.profile == 'z72' and (args.parameters or args.experimental_parameters):
        parser.error('Z72 uses the donor console experimental fixture; no Z62 parameters accepted')
    try:
        sd_card = validate_sd_card(args.profile, args.sd_card)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    qemu = args.qemu or ROOT / '.build' / f'{args.profile}-reference' / 'runtime' / 'qemu-system-arm.exe'
    work, record = stage(args.profile, qemu, args.parameters, args.experimental_parameters, args.z62_updates)
    record['host_version'] = HOST_VERSION
    record['capture_preset'] = args.capture_preset
    record['capture_properties'] = list(PRESETS[args.capture_preset])
    record['capture_pixels_implemented'] = False
    record['sd_card'] = None if sd_card is None else {
        'path': str(sd_card), 'size': sd_card.stat().st_size,
        'format': 'raw', 'snapshot': True, 'persistent_guest_writes': False,
        'filesystem_verified': False,
    }
    (work / 'session.json').write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Host launcher: ' + HOST_VERSION, flush=True)
    print('Reference experiment, not full camera emulation; no physical camera accessed.', flush=True)
    print('Session: ' + str(work), flush=True)
    print('Parameter scope: ' + json.dumps(record['parameters']), flush=True)
    print('Capture preset: ' + args.capture_preset + '; experimental handshake only, no image data.', flush=True)
    source = work / 'source'
    script = source / 'tools' / ('web_console.py' if args.profile == 'z72' else 'z62_console.py')
    sys.path.insert(0, str(source))
    argv = [str(script), '--qemu', str(qemu.resolve()),
            '--master', str(work / 'inputs/master.bin'), '--slave', str(work / 'inputs/slave.bin'),
            '--controller', str(work / 'inputs/controller.bin'),
            '--port', str(args.port or (8666 if args.profile == 'z72' else 8662))]
    if args.profile == 'z72':
        argv += ['--update-store', str(work / 'update-store')]
        if not args.no_auto_menu:
            argv.append('--auto-menu')
    else:
        argv += ['--parameters', str(work / 'parameters'), '--runs', str(work / 'runs')]
        if sd_card is not None:
            argv += ['--sd-card', str(sd_card)]
        if args.no_auto_menu:
            argv.append('--no-auto-menu')
        if args.z62_updates:
            if args.sampling_source:
                argv.append('--sampling-source')
            if args.input_trace:
                argv.append('--input-trace')
    sys.argv = argv
    original = install_native_process_adapter(work)
    subprocess.Popen = install_preset(subprocess.Popen, args.capture_preset)
    try:
        runpy.run_path(str(script), run_name='__main__')
    finally:
        subprocess.Popen = original


if __name__ == '__main__':
    main()
