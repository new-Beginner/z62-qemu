"""Original start/stop caller frames over frozen r60; no control-model changes."""
import argparse
from contextlib import redirect_stdout
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch

import trace_z62_statistics_status_lifecycle as parent
import z62_statistics_control_snapshot as control

VERSION = control.VERSION


def merge_history(samples):
    records = {'master': [], 'slave': []}; seen = {'master': {}, 'slave': {}}; gaps = []
    for sample in samples:
        for role, engine in sample['engines'].items():
            for record in engine['control_trace'] or []:
                seq = record['sequence']
                if seq in seen[role]:
                    if seen[role][seq] != record: raise ValueError('Historical control record changed')
                    continue
                prior = records[role][-1]['sequence'] if records[role] else 0
                if seq <= prior: raise ValueError('Control history moved backwards')
                if seq != prior+1:
                    gaps.append({'role': role, 'after': prior, 'next': seq,
                                 'observed_counter_seconds': sample['virtual_seconds']})
                records[role].append(record); seen[role][seq] = record
    return records, gaps


def run(output, card, group23, qemu, duration=55):
    original = parent.video.lifecycle.baseline.run
    finals, errors = [], []
    sources = {str(Path(p)): hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in
               (__file__, control.__file__, parent.__file__)}
    def instrument(*args, **kwargs):
        prior_hit = kwargs['extra_hit_hook']; prior_observe = kwargs['extra_observation_hook']
        points = kwargs['extra_points']
        if set(points) & set(control.POINTS): raise ValueError('Control probe point overlaps parent')
        kwargs['extra_points'] = {**points, **control.POINTS}
        def hit(remote, registers):
            row = prior_hit(remote, registers)
            if registers['pc'] in control.POINTS:
                value = control.capture(remote, registers)
                row['statistics_control_call'] = value
                print('STATISTICS_CONTROL_CALL', json.dumps({'pc': hex(registers['pc']),
                    'point': value['point'], 'r1': registers['r1'], 'lr': hex(registers['lr']),
                    'source_matches': value['source_instruction_matches'], 'caller': value['caller']}), flush=True)
            return row
        def observe(machine, row):
            value = prior_observe(machine, row)
            if row['virtual_seconds'] >= duration and not finals:
                try:
                    final = parent.collect(machine, {})
                    final.update(virtual_seconds=row['virtual_seconds'], final_requested_window_sample=True,
                                 sampled_after_end_row_before_debugger_cleanup=True)
                    finals.append(final)
                    print('STATISTICS_CONTROL_FINAL', json.dumps({'counter_seconds': row['virtual_seconds'],
                        'known': final['known'], 'counts': {role: e['boot']['statistics-control-count']
                        for role, e in final['engines'].items()}}), flush=True)
                except (OSError, RuntimeError, ValueError) as exc:
                    errors.append({'type': type(exc).__name__, 'message': str(exc)})
            return value
        kwargs.update(extra_hit_hook=hit, extra_observation_hook=observe)
        return original(*args, **kwargs)
    with patch.object(parent.video.lifecycle.baseline, 'run', instrument):
        previous = parent.run(output, card, group23, qemu, duration)
    trace = json.loads((output/'trace.json').read_text(encoding='utf-8'))
    calls = [{'sequence': h['sequence'], 'observer_counter_seconds': h['state']['virtual_seconds'],
              'thread': h['thread'], **h['extra_observation']['statistics_control_call']}
             for h in trace['hits'] if 'statistics_control_call' in h.get('extra_observation', {})]
    samples = [*previous['samples'], *finals]
    history, gaps = merge_history(samples)
    unchanged = all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == h for p, h in sources.items())
    known = bool(finals and finals[-1]['known'] and all(s['known'] for s in samples))
    completed = bool(previous['completed_observation'] and known and calls and not errors and unchanged and
                     all(c['source_instruction_matches'] for c in calls))
    result = {'schema': 1, 'version': VERSION, 'source_sha256': sources, 'sources_unchanged_during_run': unchanged,
        'qemu_sha256': previous['build']['binary_sha256'], 'completed_observation': completed,
        'process_closed': previous['process_closed'], 'calls': calls, 'samples': samples,
        'control_records': history, 'sequence_gaps': gaps, 'final_sample': finals[-1] if finals else None,
        'final_sample_covers_requested_end_row': known,
        'control_history_covers_requested_window': bool(completed and not gaps),
        'debugger_cleanup_interval_observed': False, 'errors': errors,
        'strict_mode_recovery_verified': previous['strict_mode_recovery_verified'],
        'completion_semantics_changed': False, 'camera_accessed': False,
        'complete_call_chain_verified': False, 'guest_algorithm_changed': False}
    with (output/'statistics-control-lifecycle.json').open('x', encoding='utf-8') as handle: json.dump(result, handle, indent=2)
    print(json.dumps({k: result[k] for k in ('completed_observation', 'control_history_covers_requested_window',
        'sequence_gaps', 'errors', 'strict_mode_recovery_verified')}), flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True); parser.add_argument('--card', type=Path, required=True)
    parser.add_argument('--group23', type=Path, required=True)
    parser.add_argument('--qemu', type=Path, default=parent.host.DEFAULT_QEMU)
    parser.add_argument('--duration', type=float, default=55)
    args = parser.parse_args(); args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.with_name(args.output.name+'-stdout.txt').open('x', encoding='utf-8') as log:
        with redirect_stdout(parent.video.lifecycle.Tee(sys.stdout, log)):
            result = run(args.output, args.card, args.group23, args.qemu.resolve(), args.duration)
    raise SystemExit(0 if result['completed_observation'] else 1)
