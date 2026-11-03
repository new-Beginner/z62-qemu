"""Recheck descriptor carriers and complete serialized roots in r57 evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

import run_z62_photo_results as host
import trace_z62_frame_source as observer

ROOT = Path(__file__).resolve().parents[1]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify(case, output):
    if output.exists():
        raise FileExistsError('Existing frame-source inventory is immutable')
    build = host.verify_build()
    read = lambda path: json.loads(path.read_text(encoding='utf-8'))
    receipt = read(case/'frame-source.json')
    life, trace = read(case/'lifecycle.json'), read(case/'trace.json')
    require(receipt['qemu_sha256'] == build['binary_sha256'], 'Frozen binary differs')
    require(receipt['completed_observation'] is True and receipt['process_closed'] is True and
            trace['process_closed'] is True and trace['detach'] == 'OK', 'Frame-source window incomplete')
    require(receipt['sources_unchanged_during_run'] is True and not receipt['read_errors'] and
            not receipt['capture_limit_reached'], 'Source/read/sampling failure')
    for name, digest in receipt['sources_sha256'].items():
        require(hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest, 'Observed source changed')
    for row in receipt['snapshots']:
        value = row['snapshot']
        items = [value['context'], value['template_core'], value['serialized_root'],
                 value['serialized_core'], value['serialized_source'], *value['descriptors']]
        for item in items:
            if item and item['captured']:
                data = bytes.fromhex(item['raw'])
                require(len(data) == item['requested_bytes'] and
                        hashlib.sha256(data).hexdigest() == item['sha256'], 'Captured packet changed')
        for descriptor in value['descriptors']:
            if descriptor['captured']:
                raw = bytes.fromhex(descriptor['raw'])
                stride, width, height = struct.unpack_from('<3H', raw, 0x26)
                require(descriptor['layout_fields'] == [width, height, stride] and
                        descriptor['dma_address'] == hex(struct.unpack_from('<I', raw, 0x34)[0]),
                        'Descriptor field replay differs')
        if value['serialized_root'] and value['serialized_root']['captured']:
            raw = bytes.fromhex(value['serialized_root']['raw'])
            require(len(raw) == 212 and value['serialized_root_flags'] ==
                {'word51_cc': struct.unpack_from('<I', raw, 204)[0],
                 'word52_d0': struct.unpack_from('<I', raw, 208)[0]}, 'Root tail was not captured')
    paired = observer.correlate(receipt['snapshots'])
    require(paired == receipt['constructor_pairs'] and not paired['incomplete'] and
            not paired['unmatched_returns'], 'Constructor frames differ')
    summaries = []
    for pair in paired['pairs']:
        entry, returned = pair['entry']['snapshot'], pair['return']['snapshot']
        if not returned['is_master_root']:
            continue
        values = struct.unpack_from('<4h', bytes.fromhex(returned['context']['raw']), 0x1ce)
        summaries.append({'virtual_seconds': pair['return']['virtual_seconds'],
            'selector_phase': pair['return']['selector_phase'],
            'descriptor_layouts': [d['layout_fields'] for d in returned['descriptors']],
            'descriptor_addresses': [d['dma_address'] for d in returned['descriptors']],
            'template_before': entry['template_core']['layout_argument'],
            'template_after': returned['template_core']['layout_argument'],
            'serialized_geometry': returned['serialized_core']['layout_argument'],
            'serialized_stride': returned['serialized_source']['stride_argument'],
            'root_flags': returned['serialized_root_flags'],
            'context_halfwords_1ce_1d0_1d2_1d4': list(values),
            'context_extent_formula': [values[0]+2*values[2], values[1]+2*values[3]],
            'formula_branch_execution_verified': False})
    require({r['selector_phase'] for r in summaries} == {0, 1, 2}, 'Missing master phase')
    files = sorted(p for p in case.parent.rglob('*') if p.is_file() and
                   p.suffix in ('.json', '.png', '.txt', '.md', '.log'))
    files.extend(p for p in (ROOT/'analysis/z62-ghidra/frame-source-r57-core').iterdir()
                 if p.is_file() and p.suffix in ('.json', '.c', '.asm', '.tsv', '.log'))
    names = ('tools/z62_frame_source_snapshot.py', 'tools/trace_z62_frame_source.py',
             'tools/verify_z62_frame_source_evidence.py', 'tests/test_z62_frame_source_snapshot.py')
    result = {'schema': 1, 'version': '2026.11.03-frame-source-evidence-r57',
        'verification_completed': True, 'qemu_sha256': build['binary_sha256'],
        'original_guest_seconds': life['final_state']['virtual_seconds'], 'original_stops': trace['stops'],
        'constructor_pairs': len(paired['pairs']), 'master_sources': summaries,
        'strict_lifecycle_assessment': life['assessment'],
        'source_sha256': {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in names},
        'evidence_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
        'actual_pixel_production_verified': False, 'physical_roi_verified': False,
        'whole_camera_verified': False}
    with output.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2)
    print(json.dumps({key: result[key] for key in ('verification_completed', 'original_guest_seconds',
        'original_stops', 'constructor_pairs', 'master_sources', 'strict_lifecycle_assessment')}, indent=2))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    verify(args.case, args.output)
