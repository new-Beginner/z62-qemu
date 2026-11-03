"""The unchanged r64 scenario with only the selected-address trace backend."""
import argparse
from contextlib import redirect_stdout
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

import trace_z62_mmio_write_lifecycle as parent
import run_z62_mmio_filter as host
import z62_mmio_filtered_trace as reader
from z62_mmio_filter_device import EVENT, WINDOWS

VERSION = '2026.11.03-mmio-filter-lifecycle-r64b'


def run(output, card, group23, qemu, gdb, duration=55, budget_mb=256):
    build = host.verify_build(qemu)
    if tuple(parent.WINDOWS) != WINDOWS: raise ValueError('Host and backend address windows differ')
    prior = parent.parent.base.install_native_process_adapter
    translated = []
    sources = {str(Path(p)): hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in
               (__file__, reader.__file__, reader.base.__file__, parent.__file__)}
    def install(work):
        original = prior(work); native = subprocess.Popen
        class FilterPopen(native):
            def __init__(self, command, *args, **kwargs):
                command = list(command)
                if Path(command[0]).name.lower() == 'qemu-system-arm.exe' and '-M' in command:
                    if '-trace' not in command or command[command.index('-trace')+1] != 'enable=memory_region_ops_write':
                        raise ValueError('Expected the one inherited write-trace selector')
                    command[command.index('-trace')+1] = 'enable='+EVENT
                    translated.append(list(command))
                super().__init__(command, *args, **kwargs)
        subprocess.Popen = FilterPopen
        return original
    with patch.object(parent.parent.base, 'install_native_process_adapter', install), \
         patch.object(parent.parent.parent, 'host', host), patch.object(parent, 'trace_reader', reader):
        observed = parent.run(output, card, group23, qemu, gdb, duration, budget_mb)
    unchanged = all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == h for p, h in sources.items())
    result = {'schema': 1, 'version': VERSION, 'build': build, 'source_sha256': sources,
        'sources_unchanged_during_run': unchanged, 'event': EVENT, 'translated_commands': translated,
        'completed_observation': bool(observed['completed_observation'] and unchanged),
        'trace_covers_requested_window': bool(observed['trace_covers_requested_window'] and unchanged),
        'trace_parse_complete': observed['trace_parse_complete'], 'log_sha256': observed['log_sha256'],
        'log_bytes': observed['log_bytes'], 'trace_budget_exceeded': observed['trace_budget_exceeded'],
        'functional_acceptance_eligible': observed['functional_acceptance_eligible'] and unchanged,
        'strict_mode_recovery_verified': observed['strict_mode_recovery_verified'],
        'model_or_guest_state_changed_by_new_trace': False, 'vmstate_version_unchanged': 52,
        'all_logged_writes_accepted': False, 'camera_accessed': False}
    with (output/'mmio-filter-lifecycle.json').open('x', encoding='utf-8') as handle: json.dump(result, handle, indent=2)
    print(json.dumps({k: result[k] for k in ('completed_observation', 'trace_covers_requested_window',
        'trace_budget_exceeded', 'log_bytes', 'strict_mode_recovery_verified')}), flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True); parser.add_argument('--card', type=Path, required=True)
    parser.add_argument('--group23', type=Path, required=True); parser.add_argument('--qemu', type=Path, default=host.DEFAULT_QEMU)
    parser.add_argument('--gdb', type=Path, default=parent.parent.host_capture.DEFAULT_GDB)
    parser.add_argument('--duration', type=float, default=55); parser.add_argument('--budget-mb', type=int, default=256)
    args = parser.parse_args()
    if not 8 <= args.budget_mb <= 512: parser.error('Trace budget must be 8..512 MiB')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.with_name(args.output.name+'-stdout.txt').open('x', encoding='utf-8') as log:
        with redirect_stdout(parent.parent.parent.control.parent.video.lifecycle.Tee(sys.stdout, log)):
            result = run(args.output, args.card, args.group23, args.qemu.resolve(), args.gdb.resolve(), args.duration, args.budget_mb)
    raise SystemExit(0 if result['completed_observation'] and result['trace_covers_requested_window'] else 1)
