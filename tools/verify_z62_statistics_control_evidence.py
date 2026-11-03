"""Verify r61 control frames, actual stores, final ring and bounded parent frames."""
import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image
import run_z62_statistics_observe as host
import z62_statistics_control_snapshot as control
from z62_statistics_control_analysis import parent_frames
from z62_statistics_engine_snapshot import parse_control_trace
import z62_scene_response as pixel_measure

ROOT = Path(__file__).resolve().parents[1]


def require(condition, message):
    if not condition: raise ValueError(message)


def integer(value):
    if type(value) is int: return value
    if type(value) is str and value.startswith('0x'): return int(value, 16)
    raise ValueError('Unexpected original register encoding')


def verify(directory):
    directory = directory.resolve(); hashes = {}
    def read(path):
        raw = path.read_bytes(); hashes[str(path)] = hashlib.sha256(raw).hexdigest()
        return json.loads(raw)
    build = host.verify_build()
    data = read(directory/'statistics-control-lifecycle.json')
    trace = read(directory/'trace.json'); session = read(directory/'session.json')
    previous = read(directory/'statistics-status-lifecycle.json')
    pixels = read(directory/'video-isp-lifecycle.json')
    firmware, firmware_sha = control.image()
    require(data['qemu_sha256'] == session['qemu_sha256'] == build['binary_sha256'], 'Run/build identity differs')
    require(session['inputs']['master.bin']['sha256'] == firmware_sha, 'Original firmware differs')
    require(data['completed_observation'] is True and previous['completed_observation'] is True and
            trace['process_closed'] is True and trace.get('detach') == 'OK' and
            trace.get('stop_reason') == 'virtual limit' and not trace.get('failure') and not trace.get('cleanup_error'),
            'Original control window did not complete cleanly')
    require(data['completion_semantics_changed'] is False and data['guest_algorithm_changed'] is False and
            data['camera_accessed'] is False and not data['errors'], 'Control semantics or boundary differs')
    for name, digest in data['source_sha256'].items():
        require(hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest, 'Control observer source changed: '+name)
        hashes[name] = digest
    for name in ('native-1.json', 'continuous-regression.json', 'video-regression.json'):
        native = read(ROOT/'analysis/z62-statistics-observe-r60'/name)
        require(native['completed'] is True, 'Parent native check failed')
        if 'binary_sha256' in native: require(native['binary_sha256'] == build['binary_sha256'], 'Native binary differs')
    samples = data['samples']; require(samples and all(s['known'] is True for s in samples), 'Unknown control sample')
    seen = {'master': {}, 'slave': {}}; records = {'master': [], 'slave': []}; gaps = []
    for sample in samples:
        for role in records:
            engine = sample['engines'][role]
            require(engine['known'] is True and not engine['errors'], 'Unknown engine status')
            for row in parse_control_trace(engine['control_trace']):
                seq = row['sequence']
                if seq in seen[role]:
                    require(row == seen[role][seq], 'Historical control record changed')
                    continue
                last = records[role][-1]['sequence'] if records[role] else 0
                require(seq > last, 'Control sequence moved backwards')
                if seq != last+1:
                    gaps.append({'role': role, 'after': last, 'next': seq,
                                 'observed_counter_seconds': sample['virtual_seconds']})
                records[role].append(row); seen[role][seq] = row
    require(records == data['control_records'] and gaps == data['sequence_gaps'], 'Derived control history differs')
    final = data['final_sample']; end = trace['observations'][-1]['virtual_seconds']
    require(final is not None and final['known'] is True and final['virtual_seconds'] >= end and
            final['sampled_after_end_row_before_debugger_cleanup'] is True,
            'Requested observation end has no final ring sample')
    hits = {h['sequence']: h for h in trace['hits']}; stores = []; analyzed = []
    for call in data['calls']:
        hit = hits[call['sequence']]; captured = hit['extra_observation']['statistics_control_call']
        require(all(captured[k] == call[k] for k in captured), 'Control call differs from original trace hit')
        pc = int(call['pc'], 16)
        require(pc in control.POINTS and call['source_instruction_matches'] is True and
                bytes.fromhex(call['source_instruction_4']) == firmware[pc-control.BASE:pc-control.BASE+4],
                'Original control instruction differs')
        require(all(integer(hit['registers'][k]) == call['registers'][k] for k in call['registers']),
                'Caller observation differs from stopped register file')
        require(call['input_sha256'] == firmware_sha, 'Control call uses another firmware')
        decoded = call['caller']
        if decoded['known']:
            site = int(decoded['callsite'], 16); raw = bytes.fromhex(decoded['raw'])
            require(raw == firmware[site-control.BASE:site-control.BASE+len(raw)], 'Observed caller bytes differ')
            require(site+len(raw) == (call['registers']['lr'] & ~1), 'Caller return does not match LR')
        frames = parent_frames(call, firmware)
        row = {**call, 'reviewed_parent_frames': frames,
               'full_original_registers': {k: integer(v) for k, v in hit['registers'].items()}}
        write = call['write_candidate']
        if write is not None:
            require(write['base_matches'] is True, 'Store base is not the observed input control')
            stores.append({'address': write['address'], 'value': write['value'], 'trace_sequence': call['sequence']})
            if frames['frames'] and int(call['pc'], 16) == 0x1020a832:
                row['logical_stop_mask_current_r5'] = row['full_original_registers']['r5']
                row['saved_parent_mask_word0'] = int.from_bytes(bytes.fromhex(call['stack']['raw'])[:4], 'little')
                row['logical_mask_matches_saved_parent'] = row['logical_stop_mask_current_r5'] == row['saved_parent_mask_word0']
        analyzed.append(row)
    ring_stores = [{'address': hex(int(r['address'], 16)), 'value': int(r['value'], 16), 'ring_sequence': r['sequence']}
                   for r in records['master'] if int(r['address'], 16) in (0x20068008, 0x2006800c)]
    require([(r['address'], r['value']) for r in stores] == [(r['address'], r['value']) for r in ring_stores],
            'GDB store observations do not match the complete observed start/stop ring')
    for captured, actual in zip(stores, ring_stores): captured['ring_sequence'] = actual['ring_sequence']
    pixel_checks = []
    for row in pixels['observations']:
        png = directory/row['lcd_file']; content = png.read_bytes()
        require(hashlib.sha256(content).hexdigest() == row['lcd_sha256'], 'LCD image changed')
        hashes[str(png)] = row['lcd_sha256']; expected = row['expected_source']
        with Image.open(png) as image:
            result = pixel_measure.measure(expected['gray'], bytes.fromhex(expected['raw_reference']),
                [bytes.fromhex(v) for v in row['raw_patches']],
                [{k: bytes.fromhex(v[k]) for k in ('y', 'uv')} for v in row['nv12_patches']], image)
        require(result == row['measure'] and all(result[k] for k in ('raw_matches', 'nv12_matches', 'lcd_matches')),
                'Original LCD pixel evidence does not recompute')
        pixel_checks.append({'kind': row['kind'], 'observer_counter_seconds': row['virtual_seconds'], 'verified': True})
    require({r['kind'] for r in pixel_checks} == {'video-before', 'video-after', 'photo-after'}, 'Missing mode pixel challenges')
    for folder in ('decompile', 'stop-dispatch', 'start-dispatch'):
        root = directory.parent/folder; manifest = read(root/'manifest.json')
        require(manifest['completed'] is True and manifest['original_unchanged'] is True and
                manifest['input_sha256'] == firmware_sha and not manifest['export_audit']['issues'], 'Unusable original static analysis')
        for path in [*root.glob('*.c'), *root.glob('*.asm')]: hashes[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    for path in (Path(__file__), Path(control.__file__), ROOT/'tools/z62_statistics_control_analysis.py'):
        hashes[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    return {'schema': 1, 'completed_verification': True, 'qemu_sha256': build['binary_sha256'],
        'input_sha256': firmware_sha, 'artifact_sha256': hashes, 'sample_count': len(samples),
        'control_record_counts': {role: len(rows) for role, rows in records.items()}, 'sequence_gaps': gaps,
        'original_store_pairs': stores, 'control_calls': analyzed, 'pixel_checks': pixel_checks,
        'observed_end_counter_seconds': end, 'final_ring_counter_seconds': final['virtual_seconds'],
        'control_history_covers_requested_window': not bool(gaps), 'debugger_cleanup_interval_observed': False,
        'strict_mode_recovery_verified': data['strict_mode_recovery_verified'], 'camera_accessed': False,
        'model_control_semantics_changed': False, 'physical_protocol_verified': False,
        'complete_call_chain_verified': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists(): raise FileExistsError('Existing verification is immutable')
    result = verify(args.directory)
    with args.output.open('x', encoding='utf-8') as handle: json.dump(result, handle, indent=2)
    print(json.dumps({k: result[k] for k in ('completed_verification', 'sample_count', 'control_record_counts',
        'sequence_gaps', 'control_history_covers_requested_window', 'strict_mode_recovery_verified')}, indent=2))
