"""Capture actual MMIO write attempts over the unchanged r63b scenario."""
import argparse
from collections import Counter
from contextlib import redirect_stdout
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from unittest.mock import patch

import trace_z62_raw_stop_host_debug as parent
import z62_mmio_write_trace as trace_reader

VERSION = '2026.11.03-mmio-write-lifecycle-r64'
WINDOWS = ((0x20060000, 0x2006c000), (0x20100000, 0x20110000), (0x20380000, 0x20381000))


def summarize(log, histories):
    selected = []; regions = Counter(); cpus = Counter(); total = 0
    with log.open('r', encoding='utf-8') as stream:
        for number, line in enumerate(stream, 1):
            row = trace_reader.parse_line(line)
            if row is None: continue
            total += 1; regions[row['region_name']] += 1; cpus[str(row['cpu'])] += 1
            if any(low <= row['address'] < high for low, high in WINDOWS):
                row.update(file_line=number, trace_entry=total)
                selected.append(row)
    result = {'total_write_attempts': total, 'selected_attempts': selected,
              'region_counts': dict(regions), 'cpu_counts': dict(cpus), 'control_pairing': None}
    try:
        result['control_pairing'] = trace_reader.pair_controls(selected, histories)
        result['control_pairing_verified'] = True
    except ValueError as exc:
        result.update(control_pairing_verified=False, pairing_error=str(exc))
    return result


def run(output, card, group23, qemu, gdb, duration=55, budget_mb=256):
    build = parent.parent.host.verify_build(qemu)
    if shutil.disk_usage(output.parent).free < 2*1024**3 or shutil.disk_usage(tempfile.gettempdir()).free < 2*1024**3:
        raise ValueError('Need 2 GiB free on trace and output volumes')
    prior_install = parent.base.install_native_process_adapter
    prior_observe = parent.base.observe_with_timeout_evidence
    launches = []; state = {'budget_exceeded': False}
    sources = {str(Path(p)): hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in
               (__file__, trace_reader.__file__, parent.__file__)}
    with tempfile.TemporaryDirectory(prefix='z62-mmio-live-') as folder:
        folder = Path(folder)
        if not str(folder).isascii(): raise ValueError('Trace log path must be ASCII')
        log = folder/'mmio-write.log'
        def install(work):
            original = prior_install(work); native = subprocess.Popen
            class TracePopen(native):
                def __init__(self, command, *args, **kwargs):
                    command = list(command)
                    candidate = Path(command[0])
                    if candidate.name.lower() == 'qemu-system-arm.exe' and '-M' in command:
                        if hashlib.sha256(candidate.read_bytes()).hexdigest() != build['binary_sha256']:
                            raise ValueError('MMIO logger would launch another binary')
                        if '-trace' in command: raise ValueError('Existing trace selection is ambiguous')
                        old_log = command[command.index('-D')+1] if '-D' in command else None
                        if '-D' in command: command[command.index('-D')+1] = log.as_posix()
                        else: command += ['-D', log.as_posix()]
                        if '-msg' in command: raise ValueError('Existing message timestamp selection is ambiguous')
                        command += ['-trace', 'enable=memory_region_ops_write', '-msg', 'timestamp=on']
                        launches.append({'previous_log_sink': old_log, 'command': command})
                    super().__init__(command, *args, **kwargs)
            subprocess.Popen = TracePopen
            return original
        def observe(snapshot, record, **kwargs):
            if log.exists() and log.stat().st_size > budget_mb*1024*1024:
                state['budget_exceeded'] = True
                raise RuntimeError('MMIO trace budget exceeded; observation must remain incomplete')
            return prior_observe(snapshot, record, **kwargs)
        with patch.object(parent.base, 'install_native_process_adapter', install), \
             patch.object(parent.base, 'observe_with_timeout_evidence', observe):
            previous = parent.run(output, card, group23, qemu, gdb, duration)
        saved = output/'mmio-write.log'
        if log.is_file(): shutil.copyfile(log, saved)
    control = json.loads((output/'statistics-control-lifecycle.json').read_text(encoding='utf-8'))
    parsed = None; error = None
    try:
        if not saved.is_file(): raise ValueError('MMIO backend did not produce a log')
        parsed = summarize(saved, control['control_records'])
    except (OSError, UnicodeError, ValueError) as exc:
        error = {'type': type(exc).__name__, 'message': str(exc)}
    unchanged = all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == h for p, h in sources.items())
    valid = bool(parsed and parsed['control_pairing_verified'] and not state['budget_exceeded'] and unchanged)
    result = {'schema': 1, 'version': VERSION, 'qemu_sha256': build['binary_sha256'],
        'source_sha256': sources, 'sources_unchanged_during_run': unchanged, 'launches': launches,
        'completed_observation': bool(previous['completed_observation'] and unchanged),
        'trace_parse_complete': parsed is not None, 'trace_parse_error': error, 'trace_budget_mb': budget_mb,
        'trace_budget_exceeded': state['budget_exceeded'], 'trace_summary': parsed,
        'log_sha256': hashlib.sha256(saved.read_bytes()).hexdigest() if saved.is_file() else None,
        'log_bytes': saved.stat().st_size if saved.is_file() else None,
        'trace_covers_requested_window': bool(valid and control['control_history_covers_requested_window']),
        'functional_acceptance_eligible': bool(previous['functional_acceptance_eligible'] and valid),
        'strict_mode_recovery_verified': previous['strict_mode_recovery_verified'],
        'all_logged_writes_accepted': False, 'trace_prefix_is_guest_virtual_time': False,
        'camera_accessed': False, 'guest_algorithm_changed': False}
    with (output/'mmio-write-lifecycle.json').open('x', encoding='utf-8') as handle: json.dump(result, handle, indent=2)
    print(json.dumps({k: result[k] for k in ('completed_observation', 'trace_parse_complete',
        'trace_parse_error', 'trace_covers_requested_window', 'trace_budget_exceeded', 'log_bytes')}), flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True); parser.add_argument('--card', type=Path, required=True)
    parser.add_argument('--group23', type=Path, required=True)
    parser.add_argument('--qemu', type=Path, default=parent.parent.host.DEFAULT_QEMU)
    parser.add_argument('--gdb', type=Path, default=parent.host_capture.DEFAULT_GDB)
    parser.add_argument('--duration', type=float, default=55); parser.add_argument('--budget-mb', type=int, default=256)
    args = parser.parse_args()
    if not 8 <= args.budget_mb <= 512: parser.error('Trace budget must be 8..512 MiB')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.with_name(args.output.name+'-stdout.txt').open('x', encoding='utf-8') as log:
        with redirect_stdout(parent.parent.control.parent.video.lifecycle.Tee(sys.stdout, log)):
            result = run(args.output, args.card, args.group23, args.qemu.resolve(), args.gdb.resolve(), args.duration, args.budget_mb)
    raise SystemExit(0 if result['completed_observation'] and result['trace_covers_requested_window'] else 1)
