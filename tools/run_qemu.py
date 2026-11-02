"""Run the native Z6II QEMU bring-up lab. Unknown hardware exits with code 2.

This runs original firmware instructions, not a mock camera UI. Engine 'both'
starts independent processes; there is deliberately no invented inter-chip IPC.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
VERSION = '0.4.0'
PAYLOADS = {
    'master': ('eg1850_mas_01700.payload.bin', '7b85aa96ea25d6b23481627313082476619ccb4dd3634a585de4ed896d350071'),
    'slave': ('eg1850_sla_01700.payload.bin', 'ed7be55b90024270c9e8227fa2effd66a0eb8f32e96de23e3d1a7a196cdaf676'),
}


def digest(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def verify_binary(directory):
    manifest = json.loads((directory / 'build-manifest.json').read_text(encoding='utf-8'))
    if manifest['lab_version'] != VERSION or manifest['machine'] != 'nikon-z6ii':
        raise ValueError('Wrong emulator version or machine manifest')
    # Manifest paths are file names, never paths escaping the selected package.
    names = [manifest['binary'], *manifest.get('runtime_dll_sha256', {})]
    if any(Path(name).name != name or '/' in name or chr(92) in name for name in names):
        raise ValueError('Unsafe runtime file name in manifest')
    binary = directory / manifest['binary']
    if digest(binary) != manifest['binary_sha256']:
        raise ValueError('QEMU binary SHA-256 mismatch; rebuild or restore the release')
    for name, expected in manifest.get('runtime_dll_sha256', {}).items():
        if digest(directory / name) != expected:
            raise ValueError(f'Runtime DLL SHA-256 mismatch: {name}')
    board = directory / 'source-overlay/nikon-z6ii.c'
    if digest(board) != manifest['board_sha256']:
        raise ValueError('Packaged board source SHA-256 mismatch')
    if 'platform_header_sha256' in manifest and digest(directory / 'source-overlay/nikon-z6ii-platform.h') != manifest['platform_header_sha256']:
        raise ValueError('Packaged platform source SHA-256 mismatch')
    return binary.resolve(), manifest


def command(binary, payload, engine, cores=1, paused=False, gdb_port=0, qmp_port=0,
            boot_config=True, trace_config=False, platform_config=True,
            auto_complete=True, blocked_control=0, completion_result=0):
    """Caller must set cwd=payload.parent; avoid ANSI argv loss on Windows."""
    if engine not in PAYLOADS or cores not in (1, 2):
        raise ValueError('Unknown engine or invalid core count')
    for value in (blocked_control, completion_result):
        if not isinstance(value, int) or not 0 <= value <= 0xFFFFFFFF:
            raise ValueError('Completion controls must be uint32 integers')
    if trace_config and boot_config and platform_config and (not auto_complete or blocked_control):
        raise ValueError('Disable --trace-config for timeout experiments (millions of status reads)')
    machine = f'nikon-z6ii,engine={engine}'
    if not boot_config:
        machine += ',boot-config=off'
    if trace_config:
        machine += ',trace-config=on'
    if not platform_config:
        machine += ',platform-config=off'
    if not auto_complete:
        machine += ',auto-complete=off'
    if blocked_control:
        machine += f',blocked-control={blocked_control}'
    if completion_result:
        machine += f',completion-result={completion_result}'
    args = [str(binary), '-machine', machine,
            '-accel', 'tcg,thread=single', '-smp', str(cores),
            '-bios', payload.name, '-display', 'none', '-nodefaults',
            '-monitor', 'none', '-serial', 'none', '-no-reboot']
    if paused:
        args.append('-S')
    if gdb_port:
        args += ['-gdb', f'tcp:127.0.0.1:{gdb_port}']
    if qmp_port:
        args += ['-qmp', f'tcp:127.0.0.1:{qmp_port},server=on,wait=off']
    return args


def parse_output(output):
    boot, events = None, []
    for line in output.splitlines():
        if line.startswith('Z6II_BOOT '):
            boot = json.loads(line[len('Z6II_BOOT '):])
        elif line.startswith('Z6II_EVENT '):
            events.append(json.loads(line[len('Z6II_EVENT '):]))
    return boot, events


def parse_configuration(output):
    return [json.loads(line[len('Z6II_CONFIG '):]) for line in output.splitlines()
            if line.startswith('Z6II_CONFIG ')]


def run(directory, payload_dir, engines, cores=1, paused=False,
        gdb_port=0, qmp_port=0, timeout=10, report_dir=None,
        boot_config=True, trace_config=False, platform_config=True,
        auto_complete=True, blocked_control=0, completion_result=0):
    binary, manifest = verify_binary(directory)
    payload_paths = {}
    for role in engines:
        name, expected = PAYLOADS[role]
        payload = payload_dir / name
        if digest(payload) != expected:
            raise ValueError(f'{role} firmware SHA-256 mismatch')
        payload_paths[role] = payload.resolve()
    # Refuse overlapping debug endpoints (e.g. GDB 1234/1235 and QMP 1235/1236).
    ports = [p + i for i in range(len(engines)) for p in (gdb_port, qmp_port) if p]
    if len(ports) != len(set(ports)) or any(not 1 <= p <= 65535 for p in ports):
        raise ValueError('Debug endpoint ports overlap or are outside 1..65535')
    processes, results = [], []
    started = time.monotonic()
    try:
        for i, role in enumerate(engines):
            args = command(binary, payload_paths[role], role, cores, paused,
                           gdb_port + i if gdb_port else 0, qmp_port + i if qmp_port else 0,
                           boot_config, trace_config, platform_config, auto_complete,
                           blocked_control, completion_result)
            process = subprocess.Popen(args, cwd=payload_paths[role].parent,
                                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            processes.append((role, process, args))
            print(f'{role}: QEMU started, PID={process.pid}; cores inside this engine={cores}', flush=True)
        for role, process, args in processes:
            remaining = max(0.05, timeout - (time.monotonic() - started)) if timeout else None
            timed_out = False
            try:
                raw, _ = process.communicate(timeout=remaining)
            except subprocess.TimeoutExpired:
                timed_out = True
                process.kill()
                raw, _ = process.communicate()
            output = raw.decode('utf-8', errors='backslashreplace')
            boot, events = parse_output(output)
            status = ('timeout' if timed_out else 'unmodeled_hardware' if
                      process.returncode == 2 and events else 'qemu_error' if
                      process.returncode else 'exited')
            result = {'engine': role, 'status': status, 'qemu_exit_code': process.returncode,
                      'command': args, 'cwd': str(payload_paths[role].parent), 'boot': boot, 'events': events,
                      'configuration_accesses': parse_configuration(output),
                      'menu_reached': False, 'dual_chip_ipc_modeled': False}
            results.append(result)
            encoding = sys.stdout.encoding or 'utf-8'
            display = output.encode(encoding, errors='backslashreplace').decode(encoding)
            print(display, end='' if display.endswith('\n') else '\n', flush=True)
            if report_dir:
                report_dir.mkdir(parents=True, exist_ok=True)
                (report_dir / f'{role}.log').write_text(output, encoding='utf-8')
    finally:
        for _, process, _ in processes:
            if process.poll() is None:
                process.kill()
                process.communicate()
    report = {'lab_version': VERSION, 'binary_sha256': manifest['binary_sha256'],
              'independent_engine_instances': len(engines),
              'inter_chip_transport_connected': False, 'results': results}
    if report_dir:
        (report_dir / 'run.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', choices=['master', 'slave', 'both'], default='master')
    parser.add_argument('--cores', type=int, choices=[1, 2], default=1,
                        help='CPU cores within each engine, not the number of EXPEED chips')
    platform_name = 'windows-x64' if os.name == 'nt' else 'linux'
    parser.add_argument('--binary-dir', type=Path,
                        default=ROOT / 'dist' / f'z6ii-qemu-v{VERSION}-{platform_name}')
    parser.add_argument('--payload-dir', type=Path, default=ROOT / 'artifacts/z6ii-1.70')
    parser.add_argument('--paused', action='store_true')
    parser.add_argument('--gdb-port', type=int, default=0)
    parser.add_argument('--qmp-port', type=int, default=0)
    parser.add_argument('--no-boot-config', action='store_true',
                        help='Negative control: stop at the original first MMIO write')
    parser.add_argument('--trace-config', action='store_true',
                        help='Record successful configuration reads/writes; avoid on timeout paths')
    parser.add_argument('--no-platform-config', action='store_true',
                        help='Restore the v0.3.0 passive model and first-status boundary')
    parser.add_argument('--no-auto-complete', action='store_true',
                        help='Experimental negative control: execute original polling timeouts')
    parser.add_argument('--blocked-control', type=lambda s: int(s, 0), default=0,
                        help='Block one observed command address; other channel remains active')
    parser.add_argument('--completion-result', type=lambda s: int(s, 0), default=0,
                        help='Experimental readonly result word injection (uint32, default zero)')
    parser.add_argument('--timeout', type=float, default=10,
                        help='Seconds; 0 waits until QEMU exits or Ctrl+C')
    parser.add_argument('--report-dir', type=Path, default=ROOT / f'analysis/qemu-v{VERSION}/latest')
    args = parser.parse_args()
    if args.timeout < 0 or args.timeout > 86400:
        parser.error('--timeout must be 0..86400 seconds')
    engines = ['master', 'slave'] if args.engine == 'both' else [args.engine]
    try:
        report = run(args.binary_dir, args.payload_dir, engines, args.cores,
                     args.paused, args.gdb_port, args.qmp_port, args.timeout, args.report_dir,
                     not args.no_boot_config, args.trace_config, not args.no_platform_config,
                     not args.no_auto_complete, args.blocked_control, args.completion_result)
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f'QEMU launch failed: {error}\n')
    except KeyboardInterrupt:
        parser.exit(130, '\nDebug session stopped.\n')
    print('Report: ' + str(args.report_dir.resolve() / 'run.json'))
    print('MENU and inter-chip transport remain unmodeled.')
    if any(row['status'] == 'qemu_error' for row in report['results']):
        raise SystemExit(1)
    if any(row['status'] != 'exited' for row in report['results']):
        raise SystemExit(2)


if __name__ == '__main__':
    main()
