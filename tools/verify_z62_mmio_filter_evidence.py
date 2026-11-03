"""Reparse filtered logs and validate observer identity, not hardware semantics."""
import argparse
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import run_z62_mmio_filter as host
import trace_z62_mmio_write_lifecycle as collector
import z62_mmio_filtered_trace as reader
from z62_mmio_filter_device import EVENT, INPUTS

ROOT = Path(__file__).resolve().parents[1]


def require(condition, message):
    if not condition: raise ValueError(message)


def verify(directory):
    directory = directory.resolve(); hashes = {}
    def read(path):
        data = path.read_bytes(); hashes[str(path)] = hashlib.sha256(data).hexdigest()
        return json.loads(data)
    build = host.verify_build()
    data = read(directory/'mmio-filter-lifecycle.json')
    inherited = read(directory/'mmio-write-lifecycle.json')
    control = read(directory/'statistics-control-lifecycle.json')
    trace = read(directory/'trace.json'); session = read(directory/'session.json')
    host_data = read(directory/'host-timeout-lifecycle.json')
    command = read(directory/'effective-command-0.json')
    ledger = read(directory.parent/'rearm-ledger-1.json')
    native_root = directory.parent/'native-filter-3'
    native = read(native_root/'native-filter-check.json')
    compatible = read(directory.parent/'native-filter-compat-1/native-compat-check.json')
    expected = build['binary_sha256']
    require(data['build']['binary_sha256'] == session['qemu_sha256'] == native['qemu_sha256'] ==
            compatible['qemu_sha256'] == expected, 'Filtered binary identity differs')
    require(native['completed'] is True and native['default_off'] is True and
            native['selected_is_exact_legacy_projection_for_fixture'] is True and
            native['actual_dma_stop_restart_regression_with_trace_on']['completed'] is True,
            'Native filtering/state/DMA proof failed')
    require(compatible['completed'] is True, 'Statistics/video regression failed')
    for row in native['logs']:
        path = native_root/row['file']
        require(hashlib.sha256(path.read_bytes()).hexdigest() == row['sha256'], 'Native log changed')
        hashes[str(path)] = row['sha256']
    for row in compatible['logs']:
        path = directory.parent/'native-filter-compat-1'/row['file']
        require(hashlib.sha256(path.read_bytes()).hexdigest() == row['sha256'], 'Compatibility log changed')
        hashes[str(path)] = row['sha256']
    new_base = read(Path(build['binary']).parent.parent/'reference-build-manifest.json')
    old_base = read(host.parent.DEFAULT_QEMU.parent.parent/'reference-build-manifest.json')
    before, after = old_base['prepared_source_file_sha256'], new_base['prepared_source_file_sha256']
    require(set(before) == set(after), 'Unexpected source files added or removed')
    delta = sorted(name for name in before if before[name] != after[name])
    require(delta == sorted(INPUTS), 'Model or unrelated source files changed')
    require(data['event'] == EVENT and '-trace' in command and command[command.index('-trace')+1] == 'enable='+EVENT,
            'Wrong trace event selected')
    require(data['model_or_guest_state_changed_by_new_trace'] is False and data['vmstate_version_unchanged'] == 52,
            'Diagnostic layer scope changed')
    require(data['completed_observation'] is True and data['trace_covers_requested_window'] is True and
            data['trace_budget_exceeded'] is False and trace['process_closed'] is True and
            trace.get('detach') == 'OK' and not trace.get('failure') and not trace.get('cleanup_error'),
            'Requested diagnostic observation did not complete')
    for document in (data, inherited, control, host_data):
        for name, digest in document['source_sha256'].items():
            require(hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest, 'Observer code changed: '+name)
            hashes[name] = digest
    log = directory/'mmio-write.log'
    digest = hashlib.sha256(log.read_bytes()).hexdigest()
    require(digest == data['log_sha256'] == inherited['log_sha256'] == ledger['log_sha256'], 'Write log changed')
    hashes[str(log)] = digest
    with patch.object(collector, 'trace_reader', reader):
        replay = collector.summarize(log, control['control_records'])
    require(replay == inherited['trace_summary'] and replay['control_pairing_verified'] is True,
            'Trace/control replay differs')
    require(ledger['source_data_sha256'] == hashes[str(directory/'mmio-write-lifecycle.json')] and
            ledger['source_control_sha256'] == hashes[str(directory/'statistics-control-lifecycle.json')],
            'Ledger input identity differs')
    host_captures = host_data['host_captures']
    if host_captures:
        capture = read(directory/'host-timeout-1/capture.json'); host_log = directory/'host-timeout-1/host-gdb.txt'
        require(capture['owner']['pid'] == trace['pid'] and capture['owner']['binary_sha256'] == expected,
                'Host debugger attached to another target')
        require(hashlib.sha256(host_log.read_bytes()).hexdigest() == capture['log_sha256'], 'Host stack log changed')
        hashes[str(host_log)] = capture['log_sha256']
        require(host_data['functional_acceptance_eligible'] is False and data['functional_acceptance_eligible'] is False,
                'Host debugger perturbation was hidden')
    require(all(t['control_commands_replayed'] is False for t in trace.get('observation_timeouts', [])), 'Controls were replayed')
    hashes[str(Path(__file__))] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    return {'schema': 1, 'completed_verification': True, 'qemu_sha256': expected, 'artifact_sha256': hashes,
        'prepared_source_delta': delta, 'default_event_disabled_native_verified': True,
        'raw_statistics_video_native_gates_passed': True, 'log_bytes': data['log_bytes'],
        'write_attempts': replay['total_write_attempts'],
        'control_ring_pairs': {role: len(rows) for role, rows in replay['control_pairing']['pairs'].items()},
        'tail_after_last_control_sample': {role: len(rows) for role, rows in replay['control_pairing']['tail_after_last_ring_sample'].items()},
        'completed_requested_observation': True, 'functional_acceptance_eligible': data['functional_acceptance_eligible'],
        'host_debugger_attached': host_data['host_debugger_attached'],
        'strict_mode_recovery_verified': data['strict_mode_recovery_verified'],
        'mode_stop_ledger': ledger['mode_stops'], 'hardware_register_semantics_verified': False,
        'all_write_attempts_accepted': False, 'camera_accessed': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists(): raise FileExistsError('Existing verification is immutable')
    result = verify(args.directory)
    with args.output.open('x', encoding='utf-8') as handle: json.dump(result, handle, indent=2)
    print(json.dumps({k: result[k] for k in ('completed_verification', 'prepared_source_delta', 'log_bytes',
        'write_attempts', 'control_ring_pairs', 'functional_acceptance_eligible', 'strict_mode_recovery_verified')}, indent=2))
