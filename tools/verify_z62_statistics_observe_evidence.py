"""Rebuild control histories from raw rings; report observations, not a fix."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import capstone
from PIL import Image

import run_z62_statistics_observe as host
from z62_statistics_engine_snapshot import parse_control_trace
import z62_scene_response as pixel_measure

ROOT = Path(__file__).resolve().parents[1]


def require(value, message):
    if not value: raise ValueError(message)


def verify(directory, status_only=False):
    directory = directory.resolve()
    root = directory.parent
    build = host.verify_build()
    hashes = {}
    def read(path):
        raw = path.read_bytes(); hashes[str(path)] = hashlib.sha256(raw).hexdigest()
        return json.loads(raw)
    data = read(directory/('statistics-status-lifecycle.json' if status_only else 'statistics-lifecycle.json'))
    if status_only:
        require(data.get('mmio_registers_collected') is False, 'QOM-only coverage is not explicit')
    previous = read(directory/'video-isp-lifecycle.json')
    lifecycle = read(directory/'lifecycle.json')
    session = read(directory/'session.json')
    trace = read(directory/'trace.json')
    require(data['build']['binary_sha256'] == previous['qemu_sha256'] == session['qemu_sha256'] ==
            build['binary_sha256'], 'Run/build binary identity differs')
    require(data['completed_observation'] is True and data['process_closed'] is True and
            previous['completed_observation'] is True and trace['process_closed'] is True and
            trace['detach'] == 'OK' and trace['stop_reason'] == 'virtual limit' and
            trace.get('failure') is None and trace.get('cleanup_error') is None,
            'Original firmware observation did not finish cleanly')
    require(data['completion_semantics_changed'] is False and data['camera_accessed'] is False and
            data['snapshots_atomic'] is False and not data['errors'], 'Invalid observer boundaries')
    pixel_checks = []
    for observation in previous['observations']:
        png_path = directory/observation['lcd_file']
        png = png_path.read_bytes(); digest = hashlib.sha256(png).hexdigest()
        require(digest == observation['lcd_sha256'], 'LCD evidence changed')
        hashes[str(png_path)] = digest
        source = observation['expected_source']
        raw = [bytes.fromhex(v) for v in observation['raw_patches']]
        nv12 = [{k: bytes.fromhex(v[k]) for k in ('y', 'uv')} for v in observation['nv12_patches']]
        with Image.open(png_path) as image:
            measured = pixel_measure.measure(source['gray'], bytes.fromhex(source['raw_reference']), raw, nv12, image)
        require(measured == observation['measure'] and all(measured[k] for k in
            ('raw_matches', 'nv12_matches', 'lcd_matches')), 'Stored pixel response does not recompute')
        pixel_checks.append({'kind': observation['kind'], 'observer_counter_seconds': observation['virtual_seconds'],
                             'gray': source['gray'], 'raw_nv12_lcd_recomputed': True})
    require({p['kind'] for p in pixel_checks} == {'video-before', 'video-after', 'photo-after'}, 'Missing mode pixel challenges')
    hashes[pixel_measure.__file__] = hashlib.sha256(Path(pixel_measure.__file__).read_bytes()).hexdigest()
    for name, digest in data['source_sha256'].items():
        require(hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest, 'Observer source changed: '+name)
        hashes[name] = digest
    native = read(root/'native-1.json')
    video = read(root/'video-regression.json')
    stats = read(root/'continuous-regression.json')
    require(native['completed'] is True and all(native['checks'][name] is True for name in (
        'default_off_no_records', 'observation_does_not_change_statistics', 'bounded_ring_keeps_sequence',
        'read_only_properties', 'slave_is_separate', 'native_two_cpu_snapshot_known')), 'Native diagnostic failed')
    require(video['completed'] is True and video['binary_sha256'] == build['binary_sha256'], 'Video regression differs')
    require(stats.get('completed') is True and stats.get('binary_sha256') == build['binary_sha256'] and
            stats.get('actual_five_output_dma') is True and stats.get('six_slots_and_guards') is True,
            'Statistics regression failed')
    records = {'master': [], 'slave': []}; seen = {'master': {}, 'slave': {}}; gaps = []
    summaries = {}
    samples = data['samples']; require(bool(samples), 'Missing two-engine snapshots')
    require(all(row['known'] is True for row in samples), 'Unknown two-engine sample')
    require(all(a['virtual_seconds'] <= b['virtual_seconds'] for a, b in zip(samples, samples[1:])),
            'Sample times moved backwards')
    for sample in samples:
        for role in records:
            engine = sample['engines'][role]
            require(engine['known'] is True and not engine['errors'], 'Unknown engine status')
            if status_only:
                require(sample.get('mmio_registers_collected') is False and
                        engine['board_cpu_index'] == (0 if role == 'master' else 2), 'Invalid QOM-only view')
            else:
                require(engine['cpu_index'] == (0 if role == 'master' else 2) and
                        len(engine['geometry_words']) == 93 and len(engine['formatter_words']) == 13 and
                        len(engine['dma']) == 5 and sum(len(ch['fields']) for ch in engine['dma']) == 73,
                        'Incomplete engine geometry/view')
            for record in parse_control_trace(engine['control_trace']):
                seq = record['sequence']
                if seq in seen[role]:
                    require(seen[role][seq] == record, 'Control ring changed a historical record')
                    continue
                prior = records[role][-1]['sequence'] if records[role] else 0
                require(seq > prior, 'New control record moved backwards')
                if seq != prior+1:
                    gaps.append({'role': role, 'after': prior, 'next': seq,
                                 'observed_virtual_seconds': sample['virtual_seconds']})
                records[role].append(record); seen[role][seq] = record
    require(records == data['control_records'] and gaps == data['sequence_gaps'], 'Stored control history differs from raw rings')
    require(data['control_history_complete'] is (not bool(gaps)), 'History completeness hides sequence gaps')
    observation_end = trace['observations'][-1]['virtual_seconds']
    history_end = samples[-1]['virtual_seconds']
    for role, history in records.items():
        firmware_path = ROOT/('artifacts/z62-reference-1.70/'+role+'.bin')
        firmware = firmware_path.read_bytes()
        firmware_sha = hashlib.sha256(firmware).hexdigest()
        require(firmware_sha == session['inputs'][role+'.bin']['sha256'], 'Original firmware changed')
        hashes[str(firmware_path)] = firmware_sha
        decoder = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB)
        instructions = []
        for pc in sorted({int(r['pc'], 16) for r in history if r['pc_valid']}):
            offset = pc-0x10020000
            instruction = next(iter(decoder.disasm(firmware[offset:offset+4], pc)), None) if 0 <= offset < len(firmware)-4 else None
            instructions.append({'pc': hex(pc), 'captured_in_original_image': instruction is not None,
                'bytes': instruction.bytes.hex() if instruction else None,
                'mnemonic': instruction.mnemonic if instruction else None,
                'operands': instruction.op_str if instruction else None,
                'is_store_instruction': bool(instruction and instruction.mnemonic.startswith('str')),
                'observed_addresses': sorted({r['address'] for r in history if int(r['pc'], 16) == pc}),
                'base_register_value_recovered': False})
        changes = []
        for name in ('raw-accepted', 'continuous-frames', 'continuous-batches'):
            series = [(s['virtual_seconds'], s['engines'][role]['input'][name]) for s in samples]
            advancing = [(t, n) for (pt, pn), (t, n) in zip(series, series[1:]) if n != pn]
            changes.append({'counter': name, 'first': series[0], 'last': series[-1],
                            'last_observed_change': advancing[-1] if advancing else None})
        first = samples[0]['engines'][role]; last = samples[-1]['engines'][role]
        relevant = [r for r in history if int(r['value'], 16) & 0x10 and int(r['address'], 16) in
                    (0x20068008, 0x2006800c, 0x20068010, 0x20068014)]
        summaries[role] = {'boot_path': last['boot_path'], 'counter_changes': changes,
            'first_boot': first['boot'], 'last_boot': last['boot'], 'last_input': last['input'],
            'last_controls': None if status_only else last['controls'], 'record_count': len(history),
            'control_pc_histogram': dict(Counter(r['pc'] for r in history if r['pc_valid'])),
            'original_instructions_at_candidate_pc': instructions,
            'all_candidate_pc_are_store_instructions': all(i['is_store_instruction'] for i in instructions) if instructions else None,
            'bit10_gate_records': relevant,
            'clear_alias_stopped_latch': [r for r in relevant if int(r['address'], 16) == 0x20068014 and
                                         r['started_before'] and not r['started_after']],
            'set_alias_while_latch_stopped': [r for r in relevant if int(r['address'], 16) == 0x20068010 and
                                            not r['started_after'] and not r['model_enable']]}
    return {'schema': 1, 'completed_verification': True, 'qemu_sha256': build['binary_sha256'],
        'verifier_source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'artifact_sha256': hashes, 'sample_count': len(samples), 'sequence_gaps': gaps,
        'engine_summary': summaries, 'selector_events': lifecycle['events'], 'mmio_registers_collected': not status_only,
        'pixel_checks': pixel_checks,
        'control_history_observer_counter_seconds': [samples[0]['virtual_seconds'], history_end],
        'observation_end_counter_seconds': observation_end,
        'unsampled_tail_counter_seconds': round(max(0, observation_end-history_end), 6),
        'full_window_control_history_verified': bool(not gaps and history_end >= observation_end),
        'strict_mode_recovery_verified': data['strict_mode_recovery_verified'],
        'pc_is_candidate_only': True, 'capstone_version': capstone.__version__,
        'physical_semantics_verified': False, 'fix_implemented': False,
        'camera_accessed': False, 'new_ready_or_dma_produced_by_observer': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True); parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--status-only', action='store_true', help='Explicitly verify QOM-only coverage, without register samples')
    args = parser.parse_args()
    if args.output.exists(): raise FileExistsError('Existing verification is immutable')
    record = verify(args.directory, args.status_only)
    with args.output.open('x', encoding='utf-8') as handle: json.dump(record, handle, indent=2)
    summary = {k: record[k] for k in ('completed_verification', 'qemu_sha256', 'sample_count',
        'sequence_gaps', 'strict_mode_recovery_verified', 'mmio_registers_collected',
        'full_window_control_history_verified', 'unsampled_tail_counter_seconds')}
    summary['engines'] = {role: {k: e[k] for k in ('record_count', 'counter_changes',
        'all_candidate_pc_are_store_instructions')} for role, e in record['engine_summary'].items()}
    print(json.dumps(summary, indent=2), flush=True)
