"""Verify r62/r63 evidence without treating failed observations as recovery."""
import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image
import run_z62_raw_stop_control as host
import z62_scene_response as pixel_measure
from z62_statistics_engine_snapshot import parse_control_trace

ROOT = Path(__file__).resolve().parents[1]


def require(condition, message):
    if not condition: raise ValueError(message)


def globals_only(command):
    values = [command[i+1] for i, token in enumerate(command[:-1]) if token == '-global']
    return ['nikon-z72-input-config.scene-initial-file=<fixed-scene>'
            if value.startswith('nikon-z72-input-config.scene-initial-file=') else value for value in values]


def verify(directory):
    directory = directory.resolve(); hashes = {}
    def read(path):
        raw = path.read_bytes(); hashes[str(path)] = hashlib.sha256(raw).hexdigest()
        return json.loads(raw)
    build = host.verify_build()
    baseline_root = ROOT/'analysis/z62-statistics-control-r61/live-1'
    baseline = read(ROOT/'analysis/z62-statistics-control-r61/verified-1.json')
    for name, digest in baseline['artifact_sha256'].items():
        require(hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest, 'Frozen r61 evidence changed: '+name)
    raw = read(directory/'raw-stop-lifecycle.json'); trace = read(directory/'trace.json')
    session = read(directory/'session.json'); control = read(directory/'statistics-control-lifecycle.json')
    pixels = read(directory/'video-isp-lifecycle.json'); producers = read(directory/'inputs.json')
    command = read(directory/'effective-command-0.json')
    old_command = read(baseline_root/'effective-command-0.json')
    old_session = read(baseline_root/'session.json'); old_pixels = read(baseline_root/'video-isp-lifecycle.json')
    require(raw['build']['binary_sha256'] == session['qemu_sha256'] == build['binary_sha256'], 'Binary identity differs')
    require(raw['raw_stop_control_enabled'] is True and raw['new_completion_injected'] is False and
            raw['guest_algorithm_changed'] is False and raw['camera_accessed'] is False, 'Experiment scope differs')
    require(session['inputs'] == old_session['inputs'], 'Firmware inputs changed')
    groups = lambda s: {name: (v['size'], v['sha256']) for name, v in s['parameters']['groups'].items()}
    require(groups(session) == groups(old_session), 'Parameter group identity differs')
    require(pixels['initial_source'] == old_pixels['initial_source'], 'Initial scene packet differs')
    new_globals = globals_only(command); stop = 'nikon-z72-boot-config.z62-raw-stop-control=on'
    require(new_globals.count(stop) == 1, 'Expected exactly one explicit RAW stop property')
    require([v for v in new_globals if v != stop] == globals_only(old_command), 'Other global model properties changed')
    for name, digest in raw['source_sha256'].items():
        require(hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest, 'RAW observer source changed: '+name)
        hashes[name] = digest
    native_root = ROOT/'analysis/z62-raw-stop-control-r62'
    native = read(native_root/'native-1.json')
    require(native['completed'] is True and native['qemu_sha256'] == build['binary_sha256'] and
            native['default_off_preserves_legacy'] is True and native['explicit_restart_real_dma'] is True and
            native['enabled_stop']['stop_request_honored'] is True and
            native['enabled_stop']['entire_four_raw_slots_preserved'] is True, 'RAW native stop gate failed')
    for name in ('statistics-regression.json', 'video-regression.json'):
        row = read(native_root/name)
        require(row['completed'] is True and row['binary_sha256'] == build['binary_sha256'], 'Default-off native regression differs')
    compatible = read(native_root/'enabled-compat-1.json')
    require(compatible['completed'] is True and compatible['qemu_sha256'] == build['binary_sha256'] and
            compatible['video_command_has_stop_option'] is True and stop in compatible['video']['command'], 'ON compatibility gate failed')
    samples = control['samples']; histories = {'master': [], 'slave': []}; seen = {'master': {}, 'slave': {}}; gaps = []
    for sample in samples:
        for role, engine in sample['engines'].items():
            for record in parse_control_trace(engine['control_trace'] or []):
                seq = record['sequence']
                if seq in seen[role]:
                    require(seen[role][seq] == record, 'Historical control record changed')
                    continue
                prior = histories[role][-1]['sequence'] if histories[role] else 0
                require(seq > prior, 'Control history moved backwards')
                if seq != prior+1:
                    gaps.append({'role': role, 'after': prior, 'next': seq, 'observed_counter_seconds': sample['virtual_seconds']})
                histories[role].append(record); seen[role][seq] = record
    require(histories == control['control_records'] and gaps == control['sequence_gaps'], 'Control ring reconstruction differs')
    assessments = []
    for row in pixels['observations']:
        png = directory/row['lcd_file']; data = png.read_bytes(); digest = hashlib.sha256(data).hexdigest()
        require(digest == row['lcd_sha256'], 'LCD evidence changed'); hashes[str(png)] = digest
        expected = row['expected_source']
        with Image.open(png) as image:
            measured = pixel_measure.measure(expected['gray'], bytes.fromhex(expected['raw_reference']),
                [bytes.fromhex(v) for v in row['raw_patches']],
                [{k: bytes.fromhex(v[k]) for k in ('y', 'uv')} for v in row['nv12_patches']], image)
        require(measured == row['measure'], 'Stored pixel values do not recompute')
        tags = {'scene-used-publish-id': 'publish_id', 'scene-used-epoch': 'epoch',
                'scene-used-frame-id': 'frame_id', 'scene-used-time-ns': 'virtual_time_ns'}
        source_matches = all(row['source'][key] == expected[value] for key, value in tags.items())
        mode_matches = row['mode_heights'][1] == 576 if row['kind'].startswith('video') else row['mode_heights'][1] in (680, 682)
        complete = bool(source_matches and mode_matches and row['display_enabled'] and row['index'] == 3 and
                        all(measured[k] for k in ('raw_matches', 'nv12_matches', 'lcd_matches')))
        require(complete is row['pixel_response_verified'] and source_matches is row['source_tags_match'], 'Pixel/source verdict differs')
        assessments.append({'kind': row['kind'], 'observer_counter_seconds': row['virtual_seconds'],
                            'source_tags_match': source_matches, 'complete_response_verified': complete})
    passed = lambda kind: any(v['kind'] == kind and v['complete_response_verified'] for v in assessments)
    require(raw['video_new_pixels_reached_factory_lcd'] is (passed('video-before') and passed('video-after')) and
            raw['photo_return_new_pixels_reached_factory_lcd'] is passed('photo-after'), 'Mode pixel summary differs')
    host_path = directory/'host-timeout-lifecycle.json'; host_doc = read(host_path) if host_path.exists() else None
    eligible = bool(raw['completed_observation'])
    if host_doc is not None:
        for name, digest in host_doc['source_sha256'].items():
            require(hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest, 'Host diagnostic source changed: '+name)
            hashes[name] = digest
        eligible = bool(raw['completed_observation'] and not host_doc['host_captures'] and not host_doc['host_capture_errors'] and
                        host_doc['sources_unchanged_during_run'])
        require(host_doc['functional_acceptance_eligible'] is eligible, 'Host debugger perturbation was hidden')
        require(host_doc['qemu_sha256'] == build['binary_sha256'], 'ASCII runtime binary differs')
        if host_doc['host_captures']:
            capture = read(directory/'host-timeout-1/capture.json')
            log = directory/'host-timeout-1/host-gdb.txt'
            require(hashlib.sha256(log.read_bytes()).hexdigest() == capture['log_sha256'], 'Host stack log changed')
            hashes[str(log)] = capture['log_sha256']
    require(all(t['control_commands_replayed'] is False for t in trace.get('observation_timeouts', [])), 'Control requests were replayed')
    for path in (Path(__file__), Path(pixel_measure.__file__)):
        hashes[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    return {'schema': 1, 'completed_verification': True, 'validation_scope': 'artifact-consistency-and-native-gates',
        'artifact_sha256': hashes, 'qemu_sha256': build['binary_sha256'], 'native_gates_passed': True,
        'global_options_only_new_raw_stop': True, 'full_argv_equivalence_verified': False,
        'completed_requested_observation': raw['completed_observation'], 'functional_acceptance_eligible': eligible,
        'strict_mode_recovery_verified': raw['strict_mode_recovery_verified'],
        'video_new_pixels_reached_factory_lcd': raw['video_new_pixels_reached_factory_lcd'],
        'photo_return_new_pixels_reached_factory_lcd': raw['photo_return_new_pixels_reached_factory_lcd'],
        'control_history_covers_requested_window': control['control_history_covers_requested_window'],
        'sample_count': len(samples), 'control_record_counts': {role: len(rows) for role, rows in histories.items()},
        'sequence_gaps': gaps, 'end_observer_counter_seconds': trace['observations'][-1]['virtual_seconds'],
        'observation_timeouts': trace.get('observation_timeouts', []), 'trace_failure': trace.get('failure'),
        'pixel_assessments': assessments, 'final_sample': control['final_sample'],
        'last_producer_sample': producers['counter_samples'][-1] if producers['counter_samples'] else None,
        'camera_accessed': False, 'physical_protocol_equivalent': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists(): raise FileExistsError('Existing verification is immutable')
    result = verify(args.directory)
    with args.output.open('x', encoding='utf-8') as handle: json.dump(result, handle, indent=2)
    print(json.dumps({k: result[k] for k in ('completed_verification', 'native_gates_passed',
        'completed_requested_observation', 'functional_acceptance_eligible', 'strict_mode_recovery_verified',
        'end_observer_counter_seconds', 'sequence_gaps')}, indent=2), flush=True)
