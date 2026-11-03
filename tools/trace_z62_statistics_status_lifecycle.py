"""Explicit QOM-only diagnostic variant; no additional CPU/HMP memory reads.

This tests the r60 observer without the intrusive two-view register sampling.
Missing register coverage is declared, never replaced with zero.
"""
import argparse
from contextlib import redirect_stdout
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

import trace_z62_video_isp_lifecycle as video
import run_z62_statistics_observe as host
import z62_statistics_engine_snapshot as contract

VERSION = '2026.11.03-statistics-status-lifecycle-r60q'


def collect(machine, cache):
    result = {'schema': 1, 'version': VERSION, 'snapshots_atomic': False, 'read_only': True,
              'mmio_registers_collected': False, 'engines': {}}
    with machine.io:
        roles = contract._discover(machine.qmp, cache)
        for role, cpu in (('master', 0), ('slave', 2)):
            row = {'boot_path': roles[role], 'board_cpu_index': cpu, 'boot': {}, 'input': {},
                   'control_trace': None, 'errors': []}
            def get(path, name, kind):
                try:
                    value = machine.qmp.command('qom-get', {'path': path, 'property': name})
                    if type(value) is not kind or (kind is int and value < 0):
                        raise ValueError('Unexpected QOM property type: '+name)
                    return value
                except (OSError, RuntimeError, ValueError) as exc:
                    row['errors'].append({'property': name, 'type': type(exc).__name__, 'message': str(exc)})
                    return None
            for name in (*contract.BOOT_BOOLS, *contract.BOOT_COUNTS):
                row['boot'][name] = get(roles[role], name, bool if name in contract.BOOT_BOOLS else int)
            for name in (*contract.INPUT_BOOLS, *contract.INPUT_COUNTS, 'continuous-reason', 'finite-reason', 'raw-last-reason'):
                kind = bool if name in contract.INPUT_BOOLS else str if name.endswith('reason') else int
                row['input'][name] = get('/machine/'+role+'-input', name, kind)
            raw = get(roles[role], 'statistics-control-trace', str)
            if raw is not None:
                try:
                    row['control_trace'] = contract.parse_control_trace(json.loads(raw))
                except (TypeError, ValueError) as exc:
                    row['errors'].append({'property': 'statistics-control-trace', 'type': type(exc).__name__, 'message': str(exc)})
            row['known'] = not row['errors']; result['engines'][role] = row
    result['known'] = all(r['known'] for r in result['engines'].values())
    return result


def run(output, card, group23, qemu, duration=55):
    build = host.verify_build(qemu)
    original = video.lifecycle.baseline.run
    samples, errors, cache, gaps = [], [], {}, []
    records = {'master': [], 'slave': []}; seen = {'master': 0, 'slave': 0}
    next_sample = 0
    sources = {str(Path(p)): hashlib.sha256(Path(p).read_bytes()).hexdigest()
               for p in (__file__, contract.__file__, video.__file__)}
    def instrument(*args, **kwargs):
        prior = kwargs['extra_observation_hook']
        def observe(machine, row):
            nonlocal next_sample
            result = prior(machine, row)
            if row['virtual_seconds'] < next_sample: return result
            next_sample = row['virtual_seconds']+2
            try:
                value = collect(machine, cache); value['virtual_seconds'] = row['virtual_seconds']
                for role, engine in value['engines'].items():
                    for record in engine['control_trace'] or []:
                        if record['sequence'] <= seen[role]: continue
                        if record['sequence'] != seen[role]+1:
                            gaps.append({'role': role, 'after': seen[role], 'next': record['sequence'],
                                         'observed_virtual_seconds': row['virtual_seconds']})
                        records[role].append(record); seen[role] = record['sequence']
                samples.append(value)
                print('STATISTICS_STATUS', json.dumps({'virtual_seconds': row['virtual_seconds'],
                    'known': value['known'], 'engines': {role: {'boot': e['boot'],
                    'enabled': e['input']['continuous-enabled'], 'frames': e['input']['continuous-frames']}
                    for role, e in value['engines'].items()}}), flush=True)
            except (OSError, RuntimeError, ValueError) as exc:
                errors.append({'virtual_seconds': row['virtual_seconds'], 'type': type(exc).__name__, 'message': str(exc)})
                print('STATISTICS_STATUS_ERROR', json.dumps(errors[-1]), flush=True)
            return result
        kwargs['extra_observation_hook'] = observe
        return original(*args, **kwargs)
    facade = SimpleNamespace(DEFAULT_QEMU=host.DEFAULT_QEMU, verify_build=host.verify_build,
        configure_command=lambda *args, **kwargs: host.configure_command(*args, **kwargs, observe=True))
    with patch.object(video, 'host', facade), patch.object(video.lifecycle.baseline, 'run', instrument):
        previous = video.run(output, card, group23, qemu, (0, 76), duration)
    unchanged = all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == h for p, h in sources.items())
    known = bool(samples and all(r['known'] for r in samples) and not errors)
    result = {'schema': 1, 'version': VERSION, 'build': build, 'source_sha256': sources,
        'sources_unchanged_during_run': unchanged, 'samples': samples, 'control_records': records,
        'sequence_gaps': gaps, 'errors': errors, 'snapshots_atomic': False, 'mmio_registers_collected': False,
        'completed_observation': bool(previous['completed_observation'] and known and unchanged),
        'control_history_complete': bool(previous['completed_observation'] and known and not gaps),
        'strict_mode_recovery_verified': previous['strict_mode_recovery_verified'],
        'process_closed': previous['process_closed'], 'completion_semantics_changed': False,
        'physical_register_semantics_verified': False, 'camera_accessed': False}
    with (output/'statistics-status-lifecycle.json').open('x', encoding='utf-8') as handle: json.dump(result, handle, indent=2)
    print(json.dumps({k: result[k] for k in ('completed_observation', 'control_history_complete',
        'strict_mode_recovery_verified', 'sequence_gaps', 'errors')}), flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True); parser.add_argument('--card', type=Path, required=True)
    parser.add_argument('--group23', type=Path, required=True); parser.add_argument('--qemu', type=Path, default=host.DEFAULT_QEMU)
    parser.add_argument('--duration', type=float, default=55); args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.with_name(args.output.name+'-stdout.txt').open('x', encoding='utf-8') as log:
        with redirect_stdout(video.lifecycle.Tee(sys.stdout, log)):
            record = run(args.output, args.card, args.group23, args.qemu.resolve(), args.duration)
    raise SystemExit(0 if record['completed_observation'] else 1)
