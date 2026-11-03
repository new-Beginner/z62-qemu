"""Bounded host-thread backtrace for this task's retained QEMU process only."""
import hashlib
from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

VERSION = '2026.11.03-host-timeout-r63b'
DEFAULT_GDB = Path('D:/Straberry-tex/c/bin/gdb.exe')
ORIGINAL_POPEN = subprocess.Popen


def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@contextmanager
def ascii_runtime(binary, expected_sha):
    binary = Path(binary).resolve(strict=True)
    manifest = json.loads((binary.parent.parent/'reference-build-manifest.json').read_text(encoding='utf-8'))
    if manifest['binary_sha256'] != expected_sha or digest(binary) != expected_sha:
        raise ValueError('ASCII runtime source binary differs')
    names = {binary.name: expected_sha, **manifest['runtime_dll_sha256']}
    with tempfile.TemporaryDirectory(prefix='z62-host-runtime-', ignore_cleanup_errors=True) as folder:
        root = Path(folder).resolve()
        if not str(root).isascii(): raise ValueError('Need an ASCII runtime path for native GDB library XML')
        for name, expected in names.items():
            if Path(name).name != name or (binary.parent/name).is_symlink():
                raise ValueError('Unexpected linked or nested runtime member')
            source, target = binary.parent/name, root/name
            if digest(source) != expected: raise ValueError('Runtime DLL source changed: '+name)
            shutil.copyfile(source, target)
            if digest(target) != expected: raise ValueError('ASCII runtime copy differs: '+name)
        yield {'binary': root/binary.name, 'file_sha256': names, 'logical_binary': str(binary)}


def guard_owner(process, owner_pid, binary, expected_sha):
    if type(owner_pid) is not int or owner_pid != process.pid:
        raise ValueError('Host capture owner PID differs')
    if process.poll() is not None:
        raise ValueError('Host capture owner already exited')
    binary = Path(binary).resolve(strict=True)
    args = process.args
    if (binary.name.lower() != 'qemu-system-arm.exe' or type(args) not in (list, tuple) or
            not args or Path(args[0]).resolve() != binary or '-M' not in args or
            args[args.index('-M')+1].split(',')[0] != 'nikon-z62-dual-lab'):
        raise ValueError('Host capture owner is not the expected Z62 QEMU')
    if digest(binary) != expected_sha:
        raise ValueError('Host capture owner binary changed')
    return {'pid': owner_pid, 'binary': str(binary), 'binary_sha256': expected_sha,
            'command_sha256': hashlib.sha256(json.dumps(list(args)).encode('utf-8')).hexdigest()}


def capture(process, owner_pid, binary, expected_sha, output, *, gdb=DEFAULT_GDB, console=None):
    if not isinstance(process, ORIGINAL_POPEN):
        raise ValueError('Host capture requires the retained native Popen instance')
    owner = guard_owner(process, owner_pid, binary, expected_sha)
    output = Path(output).resolve(); output.mkdir(parents=True, exist_ok=False)
    gdb = Path(gdb).resolve(strict=True)
    record = {'schema': 1, 'version': VERSION, 'owner': owner, 'gdb': str(gdb),
              'gdb_sha256': digest(gdb), 'completed_capture': False, 'host_debugger_attached': False,
              'host_timing_perturbed': True, 'guest_registers_or_software_written': False,
              'camera_accessed': False, 'host_debugger_launch_attempted': False}
    if console is not None:
        console = Path(console)
        record.update(console_source=str(console), console_available=console.is_file() and not console.is_symlink())
        if console.is_file() and not console.is_symlink():
            with console.open('rb') as source:
                size = console.stat().st_size; source.seek(max(0, size-2*1024*1024)); tail = source.read(2*1024*1024)
            saved = output/'qemu-console-tail.txt'
            with saved.open('xb') as target: target.write(tail)
            record.update(console_tail_sha256=digest(saved), console_source_bytes=size, console_tail_bytes=len(tail))
    started = time.monotonic()
    try:
        # A verified identical ASCII symbol copy avoids debugger filename-codepage
        # failures. The running executable and all original firmware stay untouched.
        with tempfile.TemporaryDirectory(prefix='z62-host-gdb-') as folder:
            folder = Path(folder).resolve()
            if not str(folder).isascii(): raise ValueError('Host debugger requires an ASCII symbol workspace')
            symbols = folder/'qemu-system-arm.exe'; shutil.copyfile(binary, symbols)
            if digest(symbols) != expected_sha: raise ValueError('Host symbol copy differs')
            guard_owner(process, owner_pid, binary, expected_sha)
            command = [str(gdb), '-nx', '-nh', '--batch', '-iex', 'set auto-load off',
                '--se', str(symbols), '-ex', 'set pagination off', '-ex', 'set confirm off',
                '-ex', 'attach '+str(owner_pid), '-ex', 'info threads',
                '-ex', 'thread apply all bt 24', '-ex', 'detach', '-ex', 'quit']
            record['command'] = command
            log = output/'host-gdb.txt'
            with log.open('xb') as stream:
                helper = ORIGINAL_POPEN(command, stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT,
                    cwd=folder, env=dict(os.environ, DEBUGINFOD_URLS=''),
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                record['debugger_pid'] = helper.pid; record['host_debugger_launch_attempted'] = True
                try:
                    code = helper.wait(timeout=25)
                except subprocess.TimeoutExpired:
                    helper.kill(); code = helper.wait(timeout=5); record['debugger_timeout'] = True
                record['debugger_exit_code'] = code
            text = log.read_text(encoding='utf-8', errors='replace')
            record.update(log_sha256=digest(log), stack_trace_present='#0' in text,
                          detach_reported='detached' in text.lower(), owner_alive_after=process.poll() is None)
            record['host_debugger_attached'] = record['stack_trace_present'] and 'Thread' in text
            record['library_list_parse_error'] = 'while parsing target library list' in text
            record['qemu_symbols_resolved'] = any(name in text for name in ('qemu_main_loop', 'qemu_tcg_', 'main_loop_wait'))
            record['completed_capture'] = bool(code == 0 and record['stack_trace_present'] and
                record['detach_reported'] and record['owner_alive_after'] and
                not record['library_list_parse_error'] and record['qemu_symbols_resolved'])
    except Exception as exc:
        record['failure'] = {'type': type(exc).__name__, 'message': str(exc)}
    record['host_elapsed_seconds'] = round(time.monotonic()-started, 3)
    with (output/'capture.json').open('x', encoding='utf-8') as handle: json.dump(record, handle, indent=2)
    return record
