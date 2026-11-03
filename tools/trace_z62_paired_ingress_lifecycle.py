"""Original photo/video scenario plus explicit C input; no host debugger attach."""
import argparse
from contextlib import redirect_stdout
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

import run_z62_paired_ingress as host
import trace_z62_statistics_control_lifecycle as control

VERSION = '2026.11.03-paired-ingress-lifecycle-r65'
FIELDS = {'active': bool, 'attempts': int, 'frames': int, 'bytes': int, 'rejected': int,
          'blocked': int, 'publish-id': int, 'dma-time-ns': int, 'reason': str}


def run(output, card, group23, qemu, duration=55):
    build = host.verify_build(qemu)
    sources = {str(Path(p)): hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in
               (__file__, host.__file__, control.__file__, control.parent.__file__)}
    prior = control.parent.collect
    def collect(machine, cache):
        sample = prior(machine, cache)
        with machine.io:
            for role, engine in sample['engines'].items():
                engine['paired_ingress'] = {}
                for name, kind in FIELDS.items():
                    try:
                        value = machine.qmp.command('qom-get', {'path': engine['boot_path'],
                            'property': 'paired-ingress-'+name})
                        if type(value) is not kind or (kind is int and value < 0):
                            raise ValueError('Unexpected paired input QOM type: '+name)
                        engine['paired_ingress'][name] = value
                    except (OSError, RuntimeError, ValueError) as exc:
                        engine['paired_ingress'][name] = None
                        engine['errors'].append({'property': 'paired-ingress-'+name,
                            'type': type(exc).__name__, 'message': str(exc)})
                engine['known'] = not engine['errors']
        sample['known'] = all(e['known'] for e in sample['engines'].values())
        return sample
    facade = SimpleNamespace(DEFAULT_QEMU=host.DEFAULT_QEMU, verify_build=host.verify_build,
        configure_command=lambda *args, **kwargs: host.configure_command(*args, **kwargs,
            stop_control=True, paired=True))
    with patch.object(control.parent, 'host', facade), patch.object(control.parent, 'collect', collect):
        observed = control.run(output, card, group23, qemu, duration)
    pixels = json.loads((output/'video-isp-lifecycle.json').read_text(encoding='utf-8'))
    unchanged = all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == h for p, h in sources.items())
    result = {'schema': 1, 'version': VERSION, 'build': build, 'source_sha256': sources,
        'sources_unchanged_during_run': unchanged,
        'completed_observation': bool(observed['completed_observation'] and unchanged),
        'process_closed': observed['process_closed'], 'host_debugger_attached': False,
        'functional_acceptance_eligible': bool(observed['completed_observation'] and unchanged),
        'strict_mode_recovery_verified': observed['strict_mode_recovery_verified'],
        'video_new_pixels_reached_factory_lcd': pixels['video_new_pixels_reached_factory_lcd'],
        'photo_return_new_pixels_reached_factory_lcd': pixels['photo_return_new_pixels_reached_factory_lcd'],
        'source_samples': [{'observer_counter_seconds': s['virtual_seconds'],
            'known': s['known'], 'engines': {role: e['paired_ingress'] for role, e in s['engines'].items()}}
            for s in observed['samples']],
        'final_sample': observed['final_sample'], 'sequence_gaps': observed['sequence_gaps'],
        'errors': observed['errors'], 'implementation_level': 'C', 'statistics_generated_by_new_source': False,
        'guest_algorithm_changed': False, 'physical_protocol_equivalent': False, 'camera_accessed': False}
    with (output/'paired-ingress-lifecycle.json').open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2)
    print(json.dumps({k: result[k] for k in ('completed_observation', 'process_closed',
        'strict_mode_recovery_verified', 'video_new_pixels_reached_factory_lcd',
        'photo_return_new_pixels_reached_factory_lcd')}, indent=2), flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--card', type=Path, required=True)
    parser.add_argument('--group23', type=Path, required=True)
    parser.add_argument('--qemu', type=Path, default=host.DEFAULT_QEMU)
    parser.add_argument('--duration', type=float, default=55)
    args = parser.parse_args()
    if not 55 <= args.duration <= 90:
        parser.error('Full three-stage scenario needs duration 55..90')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.with_name(args.output.name+'-stdout.txt').open('x', encoding='utf-8') as log:
        with redirect_stdout(control.parent.video.lifecycle.Tee(sys.stdout, log)):
            result = run(args.output, args.card, args.group23, args.qemu.resolve(), args.duration)
    raise SystemExit(0 if result['completed_observation'] else 1)
