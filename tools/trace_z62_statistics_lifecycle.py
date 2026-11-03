"""Observe both statistics engines during the unchanged factory mode cycle."""
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
import z62_statistics_engine_snapshot as snapshot

VERSION = '2026.11.03-statistics-lifecycle-r60'


def run(output, card, group23, qemu, origin=(0, 76), duration=55):
    build = host.verify_build(qemu)
    original = video.lifecycle.baseline.run
    samples, errors, cache = [], [], {}
    seen = {'master': 0, 'slave': 0}
    records = {'master': [], 'slave': []}
    gaps = []
    next_sample = 0
    sources = {str(Path(p)): hashlib.sha256(Path(p).read_bytes()).hexdigest()
               for p in (__file__, snapshot.__file__, video.__file__)}

    def instrument(*args, **kwargs):
        prior = kwargs['extra_observation_hook']
        def observe(machine, row):
            nonlocal next_sample
            result = prior(machine, row)
            if row['virtual_seconds'] < next_sample: return result
            next_sample = row['virtual_seconds']+2
            try:
                value = snapshot.collect(machine, cache)
                value['virtual_seconds'] = row['virtual_seconds']
                for role, engine in value['engines'].items():
                    ring = engine['control_trace']
                    if ring is None: continue
                    fresh = [r for r in ring if r['sequence'] > seen[role]]
                    for record in fresh:
                        if record['sequence'] != seen[role]+1:
                            gaps.append({'role': role, 'after': seen[role], 'next': record['sequence'],
                                         'observed_virtual_seconds': row['virtual_seconds']})
                        records[role].append(record)
                        seen[role] = record['sequence']
                    # Full ring kept in the raw sample for independent replay.
                samples.append(value)
                summary = {role: {'started': e['boot']['statistics-model-started'],
                    'mask': e['controls']['0x20068010'], 'enabled': e['input']['continuous-enabled'],
                    'active': e['input']['continuous-active'], 'frames': e['input']['continuous-frames'],
                    'controls': e['boot']['statistics-control-count'], 'errors': len(e['errors'])}
                    for role, e in value['engines'].items()}
                print('STATISTICS_ENGINES', json.dumps({'virtual_seconds': row['virtual_seconds'],
                    'known': value['known'], 'engines': summary}), flush=True)
            except (OSError, RuntimeError, ValueError, KeyError) as exc:
                errors.append({'virtual_seconds': row['virtual_seconds'], 'type': type(exc).__name__, 'message': str(exc)})
                print('STATISTICS_OBSERVATION_ERROR', json.dumps(errors[-1]), flush=True)
            return result
        kwargs['extra_observation_hook'] = observe
        return original(*args, **kwargs)

    facade = SimpleNamespace(DEFAULT_QEMU=host.DEFAULT_QEMU, verify_build=host.verify_build,
        configure_command=lambda *args, **kwargs: host.configure_command(*args, **kwargs, observe=True))
    with patch.object(video, 'host', facade), patch.object(video.lifecycle.baseline, 'run', instrument):
        previous = video.run(output, card, group23, qemu, origin, duration)
    unchanged = all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == h for p, h in sources.items())
    result = {'schema': 1, 'version': VERSION, 'build': build, 'source_sha256': sources,
        'sources_unchanged_during_run': unchanged, 'samples': samples, 'control_records': records,
        'sequence_gaps': gaps, 'errors': errors, 'snapshots_atomic': False,
        'completed_observation': bool(previous['completed_observation'] and samples and
            all(r['known'] for r in samples) and unchanged and not errors),
        'control_history_complete': bool(samples and not gaps and not errors and
            all(r['known'] for r in samples)),
        'strict_mode_recovery_verified': previous['strict_mode_recovery_verified'],
        'process_closed': previous['process_closed'], 'completion_semantics_changed': False,
        'physical_register_semantics_verified': False, 'camera_accessed': False}
    with (output/'statistics-lifecycle.json').open('x', encoding='utf-8') as handle: json.dump(result, handle, indent=2)
    print(json.dumps({k: result[k] for k in ('completed_observation', 'control_history_complete',
        'strict_mode_recovery_verified', 'sequence_gaps', 'errors')}), flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--card', type=Path, required=True)
    parser.add_argument('--group23', type=Path, required=True)
    parser.add_argument('--qemu', type=Path, default=host.DEFAULT_QEMU)
    parser.add_argument('--origin-x', type=int, default=0); parser.add_argument('--origin-y', type=int, default=76)
    parser.add_argument('--duration', type=float, default=55)
    args = parser.parse_args(); args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.with_name(args.output.name+'-stdout.txt').open('x', encoding='utf-8') as log:
        with redirect_stdout(video.lifecycle.Tee(sys.stdout, log)):
            record = run(args.output, args.card, args.group23, args.qemu.resolve(), (args.origin_x, args.origin_y), args.duration)
    raise SystemExit(0 if record['completed_observation'] else 1)
