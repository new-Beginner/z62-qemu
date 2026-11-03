"""Recheck r53 identities and completed observations without promoting recovery."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

import run_z62_photo_results as host

ROOT = Path(__file__).resolve().parents[1]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify(case, output):
    if output.exists():
        raise FileExistsError('Existing r53 evidence inventory is immutable')
    build = host.verify_build()
    case = case.resolve(strict=True)
    read = lambda p: json.loads(p.read_text(encoding='utf-8'))
    receipts = {name: read(case/(name+'.json')) for name in
        ('photo-results-lifecycle', 'grid-geometry-lifecycle', 'inputs', 'pipeline', 'lifecycle', 'trace')}
    for name, row in receipts.items():
        if 'qemu_sha256' in row:
            require(row['qemu_sha256'] == build['binary_sha256'], 'Binary mismatch in '+name)
    require(receipts['photo-results-lifecycle']['completed_observation'] is True,
            'r53 observation did not complete')
    require(receipts['inputs']['sources_unchanged_during_run'] is True, 'Observed sources changed')
    for path, digest in receipts['inputs']['sources_sha256'].items():
        require(hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest, 'Source changed: '+path)
    require(receipts['pipeline']['completed_capture'] is True and
            receipts['pipeline']['capture_phases'] == [0, 1, 2] and
            not receipts['pipeline']['read_errors'], 'Incomplete pipeline capture')
    life, trace = receipts['lifecycle'], receipts['trace']
    require(life['completed'] is True and life['process_closed'] is True and
            trace['process_closed'] is True and trace['detach'] == 'OK', 'Unclosed original session')
    require(trace['stop_reason'] == 'virtual limit' and trace['guest_state_patched'] is False,
            'Observation boundary or original state differs')
    counters = receipts['inputs']['counter_samples']
    require(all(r['known'] is True and not r['errors'] for r in counters), 'Unknown producer sample')
    low, high = [e['virtual_seconds'] for e in life['events']]
    require([e['level'] for e in life['events']] == [0, 1] and low < high, 'Unexpected selector inputs')
    waits = life['original_waits']
    phases = {}
    for name, start, end in (('initial', 0, low), ('selector-low', low, high),
                              ('returned-high', high, float('inf'))):
        selected = [w for w in waits['waits'] if start <= w['call']['guest_seconds'] < end]
        phases[name] = {'paired': len(selected),
            'return_r0': dict(Counter(str(w['return']['snapshot']['return_r0']) for w in selected)),
            'wait_seconds': [w['guest_seconds_wait'] for w in selected]}
    native, legacy = read(case.parent/'native-1.json'), read(case.parent/'legacy-results-1.json')
    require(native['completed'] is True and native['firmware_executed'] is False and
            native['actual_twelve_outputs'] is True and native['active_680_extent'] is True,
            'Native photo layout verification missing')
    require(legacy['completed'] is True and legacy['binary_sha256'] == build['binary_sha256'],
            'Legacy result verification missing')
    for frame in life['frames']:
        require(hashlib.sha256((case/frame['file']).read_bytes()).hexdigest() == frame['sha256'],
                'LCD image changed')
    source_names = ('tools/z62_photo_results_device.py', 'tools/build_z62_photo_results.py',
        'tools/run_z62_photo_results.py', 'tools/probe_z62_photo_results.py',
        'tools/trace_z62_photo_results_lifecycle.py', 'tools/check_z62_photo_results_profile.py',
        'tools/verify_z62_photo_results_evidence.py', 'tests/test_z62_photo_results.py',
        'tests/native/z62_photo_results_profile_test.c',
        'qemu/z62-photo-results/nikon-z62-photo-results-profile.h')
    source_hashes = {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in source_names}
    evidence = sorted(p for p in case.parent.rglob('*') if p.is_file() and p.suffix in ('.json', '.png', '.txt', '.log', '.md'))
    evidence_hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in evidence}
    result = {'schema': 1, 'version': '2026.11.03-photo-results-evidence-r53',
        'verification_completed': True, 'qemu_sha256': build['binary_sha256'],
        'original_guest_seconds': life['final_state']['virtual_seconds'],
        'original_stops': trace['stops'], 'original_ready_callback_hits': life['original_ready_callback_hits'],
        'selector_events': life['events'], 'original_waits_by_call_phase': phases,
        'unreturned_wait_count': len(waits['incomplete']),
        'unmatched_return_count': len(waits['outside_scope']),
        'last_producer_sample': counters[-1], 'last_lifecycle_sample': life['samples'][-1],
        'strict_recovery_assessment': life['assessment'],
        'source_sha256': source_hashes, 'evidence_sha256': evidence_hashes,
        'physical_cache_lifetime_verified': False, 'new_scene_response_verified': False,
        'video_verified': False, 'whole_camera_verified': False, 'camera_accessed': False}
    with output.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2)
    print(json.dumps({k: result[k] for k in ('verification_completed', 'original_guest_seconds',
        'original_stops', 'original_ready_callback_hits', 'original_waits_by_call_phase',
        'unreturned_wait_count', 'unmatched_return_count', 'strict_recovery_assessment')}, indent=2))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    verify(args.case, args.output)
