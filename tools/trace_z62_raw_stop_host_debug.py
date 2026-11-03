"""r62 diagnostic with verified ASCII runtime and one owned host timeout dump.

Host attachment perturbs scheduling. A run that attached the host debugger is
explicitly ineligible as a functional mode-recovery acceptance run.
"""
import argparse
from contextlib import redirect_stdout
import hashlib
import inspect
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

import trace_z62_raw_stop_lifecycle as parent
import trace_z62_upper_waits as base
import z62_host_timeout_capture as host_capture

VERSION = '2026.11.03-host-timeout-profile-r63b'


def run(output, card, group23, qemu, gdb, duration=55):
    build = parent.host.verify_build(qemu)
    prior_install = base.install_native_process_adapter
    prior_observe = base.observe_with_timeout_evidence
    launches, captures, capture_errors = [], [], []
    sources = {str(Path(p)): hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in
               (__file__, host_capture.__file__, parent.__file__, base.__file__)}
    with host_capture.ascii_runtime(qemu, build['binary_sha256']) as staged:
        actual_binary = staged['binary']
        def install(work):
            original = prior_install(work)
            native = subprocess.Popen
            class AsciiPopen(native):
                def __init__(self, command, *args, **kwargs):
                    command = list(command)
                    owned = Path(command[0]).resolve() == qemu.resolve()
                    if owned: command[0] = str(actual_binary)
                    super().__init__(command, *args, **kwargs)
                    if owned: launches.append({'pid': self.pid, 'actual_command': list(self.args)})
            subprocess.Popen = AsciiPopen
            return original
        def capture_once(snapshot, record):
            if captures or capture_errors: return
            try:
                # The inspected baseline snapshot closes over this exact Machine.
                # No process enumeration or arbitrary PID attachment is used.
                machine = inspect.getclosurevars(snapshot).nonlocals.get('machine')
                if machine is None: raise ValueError('Snapshot has no owned Machine closure')
                process = machine.process; owner = record['pid']
                host_capture.guard_owner(process, owner, actual_binary, build['binary_sha256'])
                work = Path(machine.work).resolve()
                console = work/'console.txt'
                if not console.resolve().is_relative_to(work): raise ValueError('Console escapes owned work')
                capture = host_capture.capture(process, owner, actual_binary, build['binary_sha256'],
                    output/'host-timeout-1', gdb=gdb, console=console)
                capture['trigger'] = dict(record['observation_timeouts'][-1])
                captures.append(capture)
                print('OWNED_HOST_TIMEOUT_CAPTURE', json.dumps({k: capture.get(k) for k in
                    ('completed_capture', 'qemu_symbols_resolved', 'library_list_parse_error', 'failure')}), flush=True)
            except Exception as exc:
                capture_errors.append({'type': type(exc).__name__, 'message': str(exc)})
                print('HOST_CAPTURE_REFUSED_OR_FAILED', json.dumps(capture_errors[-1]), flush=True)
        def observe(snapshot, record, **kwargs):
            try:
                result = prior_observe(snapshot, record, **kwargs)
            except TimeoutError:
                capture_once(snapshot, record)
                raise
            if result[0] is None: capture_once(snapshot, record)
            return result
        with patch.object(base, 'install_native_process_adapter', install), \
             patch.object(base, 'observe_with_timeout_evidence', observe):
            previous = parent.run(output, card, group23, qemu, duration)
    unchanged = all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == h for p, h in sources.items())
    result = {'schema': 1, 'version': VERSION, 'qemu_sha256': build['binary_sha256'],
        'logical_qemu': str(qemu), 'ascii_runtime_file_sha256': staged['file_sha256'],
        'source_sha256': sources, 'sources_unchanged_during_run': unchanged,
        'launches': launches, 'host_captures': captures, 'host_capture_errors': capture_errors,
        'completed_observation': bool(previous['completed_observation'] and unchanged),
        'functional_acceptance_eligible': bool(previous['completed_observation'] and not captures and not capture_errors and unchanged),
        'host_debugger_attached': any(c.get('host_debugger_attached') for c in captures),
        'strict_mode_recovery_verified': previous['strict_mode_recovery_verified'],
        'video_new_pixels_reached_factory_lcd': previous['video_new_pixels_reached_factory_lcd'],
        'photo_return_new_pixels_reached_factory_lcd': previous['photo_return_new_pixels_reached_factory_lcd'],
        'camera_accessed': False, 'guest_algorithm_changed': False, 'control_commands_replayed': False}
    with (output/'host-timeout-lifecycle.json').open('x', encoding='utf-8') as handle: json.dump(result, handle, indent=2)
    print(json.dumps({k: result[k] for k in ('completed_observation', 'functional_acceptance_eligible',
        'host_debugger_attached', 'strict_mode_recovery_verified', 'host_capture_errors')}), flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True); parser.add_argument('--card', type=Path, required=True)
    parser.add_argument('--group23', type=Path, required=True); parser.add_argument('--qemu', type=Path, default=parent.host.DEFAULT_QEMU)
    parser.add_argument('--gdb', type=Path, default=host_capture.DEFAULT_GDB); parser.add_argument('--duration', type=float, default=55)
    args = parser.parse_args(); args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.with_name(args.output.name+'-stdout.txt').open('x', encoding='utf-8') as log:
        with redirect_stdout(parent.control.parent.video.lifecycle.Tee(sys.stdout, log)):
            result = run(args.output, args.card, args.group23, args.qemu.resolve(), args.gdb.resolve(), args.duration)
    raise SystemExit(0 if result['completed_observation'] else 1)
