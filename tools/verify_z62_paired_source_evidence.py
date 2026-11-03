"""Recheck r56 source evidence while preserving its sampling-limit failure."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

import run_z62_photo_results as host
import trace_z62_paired_source as observer

ROOT = Path(__file__).resolve().parents[1]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify(case, output):
    if output.exists():
        raise FileExistsError('Existing paired source verification is immutable')
    build = host.verify_build()
    read = lambda path: json.loads(path.read_text(encoding='utf-8'))
    receipt = read(case/'paired-source.json')
    trace, life = read(case/'trace.json'), read(case/'lifecycle.json')
    require(receipt['qemu_sha256'] == build['binary_sha256'], 'Frozen binary differs')
    require(receipt['parent_completed_observation'] is True and receipt['process_closed'] is True and
            trace['process_closed'] is True and trace['detach'] == 'OK', 'Parent window did not close')
    require(receipt['sources_unchanged_during_run'] is True and not receipt['read_errors'], 'Read/source failure')
    for name, digest in receipt['sources_sha256'].items():
        require(hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest, 'Observed source changed')
    rows = receipt['snapshots']
    for row in rows:
        data = row['snapshot']
        for name in ('core', 'source', 'outputs', 'root', 'object', 'entry_stack'):
            item = data.get(name)
            if item and item['captured']:
                payload = bytes.fromhex(item['raw'])
                require(len(payload) == item['requested_bytes'] and
                        hashlib.sha256(payload).hexdigest() == item['sha256'], 'Packet content differs')
        core = data['core']
        if core['captured']:
            values = struct.unpack_from('<4H', bytes.fromhex(core['raw']), 44)
            require(list(values[:2]) == core['origin_argument'] and list(values[2:]) == core['layout_argument'],
                    'Geometry argument cannot be replayed')
        source = data.get('source')
        if source and source['captured']:
            require(struct.unpack_from('<H', bytes.fromhex(source['raw']), 76)[0] == source['stride_argument'],
                    'Stride argument cannot be replayed')
    paired = observer.correlate(rows)
    require(paired == receipt['geometry_call_pairs'], 'Original frame pairing differs')
    require(observer.coverage(rows) == receipt['known_dispatch_source_phases'], 'Source phase coverage differs')
    count = receipt['hit_counts']
    limited = any(value > 100 for value in count.values())
    require(limited == receipt['capture_limit_reached'], 'Sampling limit differs')
    if limited:
        require(receipt['completed_observation'] is False, 'Sampling failure was promoted to success')
    summary = [{'virtual_seconds': row['virtual_seconds'], 'selector_phase': row['selector_phase'],
        'geometry': row['snapshot']['core']['layout_argument'],
        'stride': row['snapshot']['source']['stride_argument'],
        'ring': row['snapshot']['source']['first_ring_argument'],
        'upstream': row['snapshot']['upstream_before']['layout_fields']}
        for row in rows if row['snapshot']['kind'] == 'dispatch-entry' and
        row['snapshot']['core']['captured'] and row['snapshot']['source']['captured']]
    artifact_paths = sorted(p for p in case.parent.rglob('*') if p.is_file() and
                            p.suffix in ('.json', '.png', '.md', '.txt', '.log'))
    export_dirs = ('paired-source-r56-dispatch', 'paired-source-r56-wrappers', 'paired-source-r56-builder',
                   'paired-source-r56-packets', 'paired-source-r56-origin', 'paired-source-r56-raw-layout')
    for name in export_dirs:
        artifact_paths.extend(p for p in (ROOT/'analysis/z62-ghidra'/name).iterdir() if
                              p.is_file() and p.suffix in ('.json', '.c', '.asm', '.tsv', '.log'))
    source_names = ('tools/z62_paired_source_snapshot.py', 'tools/trace_z62_paired_source.py',
                    'tools/verify_z62_paired_source_evidence.py', 'tests/test_z62_paired_source_snapshot.py')
    result = {'schema': 1, 'version': '2026.11.03-paired-source-evidence-r56',
        'verification_completed': True, 'original_observer_completed': receipt['completed_observation'],
        'parent_observation_completed': receipt['parent_completed_observation'],
        'sampling_limit_preserved': limited, 'root_prefix_words': 52,
        'known_full_record_minimum_words': 53, 'tail_word52_captured': False,
        'original_guest_seconds': life['final_state']['virtual_seconds'], 'original_stops': trace['stops'],
        'qemu_sha256': build['binary_sha256'], 'source_packets': summary,
        'original_geometry_pairs': len(paired['pairs']), 'incomplete_pairs': len(paired['incomplete']),
        'unmatched_returns': len(paired['unmatched_returns']),
        'strict_lifecycle_assessment': life['assessment'],
        'source_sha256': {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in source_names},
        'evidence_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in artifact_paths},
        'actual_pixel_production_verified': False, 'whole_camera_verified': False}
    with output.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2)
    print(json.dumps({key: result[key] for key in ('verification_completed', 'original_observer_completed',
        'parent_observation_completed', 'sampling_limit_preserved', 'original_guest_seconds', 'original_stops',
        'source_packets', 'original_geometry_pairs', 'incomplete_pairs', 'unmatched_returns')}, indent=2))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    verify(args.case, args.output)
