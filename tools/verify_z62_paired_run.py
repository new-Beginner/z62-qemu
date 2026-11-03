"""Replay a selected r66 run without relocating or upgrading interrupted evidence."""
import argparse
import hashlib
import json
import math
from pathlib import Path
from PIL import Image

import run_z62_paired_handoff as host
import z62_scene_packet as packet
import z62_scene_response as measure

ROOT = Path(__file__).resolve().parents[1]
VERSION = '2026.11.03-paired-run-evidence-r67b'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def flag(record, name):
    value = record.get(name)
    require(type(value) is bool, 'Missing or invalid boolean: '+name)
    return value


def assess_window(live, trace, control, minimum_seconds=55):
    final = control.get('final_sample')
    end = final.get('virtual_seconds') if isinstance(final, dict) else None
    end_known = (isinstance(final, dict) and final.get('known') is True and
                 type(end) in (int, float) and math.isfinite(end) and end >= minimum_seconds)
    complete = bool(trace.get('process_closed') is True and trace.get('detach') == 'OK' and
        not trace.get('failure') and not trace.get('cleanup_error') and
        flag(live, 'sources_unchanged_during_run') and flag(control, 'completed_observation') and
        flag(control, 'control_history_covers_requested_window') and
        flag(control, 'final_sample_covers_requested_end_row') and
        not control.get('sequence_gaps') and not control.get('errors') and end_known)
    eligible = bool(complete and not flag(live, 'host_debugger_attached'))
    require(flag(live, 'completed_observation') == complete, 'Recorded window completeness differs')
    require(flag(live, 'functional_acceptance_eligible') == eligible, 'Recorded window eligibility differs')
    return {'complete': complete, 'eligible': eligible}


def replay_pixel(row, image):
    source = row['expected_source']
    actual = measure.measure(source['gray'], bytes.fromhex(source['raw_reference']),
        [bytes.fromhex(p) for p in row['raw_patches']],
        [{'y': bytes.fromhex(p['y']), 'uv': bytes.fromhex(p['uv'])} for p in row['nv12_patches']], image)
    require(actual == row['measure'], 'Saved pixel measurement differs from replay')
    tags = {'scene-used-publish-id': 'publish_id', 'scene-used-epoch': 'epoch',
            'scene-used-frame-id': 'frame_id', 'scene-used-time-ns': 'virtual_time_ns'}
    tag_match = all(type(source[name]) is int and row['source'].get(key) == source[name]
                    for key, name in tags.items())
    require(flag(row, 'source_tags_match') == tag_match, 'Recorded source tag verdict differs')
    heights = row['mode_heights']
    require(len(heights) == 3, 'Incomplete mode geometry')
    require(row['kind'] in ('video-before', 'video-after', 'photo-after'), 'Unknown pixel observation phase')
    mode = heights[1] == 576 if row['kind'].startswith('video') else heights[1] in (680, 682)
    response = bool(tag_match and mode and row['display_enabled'] is True and row['index'] == 3 and
                    all(actual[k] for k in ('raw_matches', 'nv12_matches', 'lcd_matches')))
    require(flag(row, 'pixel_response_verified') == response, 'Recorded pixel response verdict differs')
    return response


def qualify_host_context(state, profile):
    captures = profile['host_captures']; errors = profile['host_capture_errors']
    attached = any(c.get('host_debugger_attached') is True for c in captures)
    require(flag(profile, 'host_debugger_attached') == attached, 'Recorded host attachment differs')
    require(flag(profile, 'completed_observation') == state['complete'] and
            flag(profile, 'sources_unchanged_during_run'), 'Host diagnostic observation scope differs')
    eligible = bool(state['eligible'] and not captures and not errors)
    require(flag(profile, 'functional_acceptance_eligible') == eligible, 'Recorded host eligibility differs')
    return {'complete': state['complete'], 'eligible': eligible}


def verify(native_case, run_directory, *, allow_interrupted=False, minimum_seconds=55):
    native_case = native_case.resolve(); case = run_directory.resolve()
    hashes = {}
    def digest(path):
        path = Path(path).resolve()
        value = hashlib.sha256(path.read_bytes()).hexdigest()
        hashes[str(path)] = value
        return value
    def read(path):
        digest(path)
        return json.loads(path.read_text(encoding='utf-8'))
    build = host.verify_build()
    proof = read(native_case/'verified-native-1.json')
    expected = build['binary_sha256']
    require(proof.get('completed_verification') is True and
            proof.get('native_handoff_regression_verified') is True and
            proof['qemu_sha256'] == expected and proof['vmstate_version'] == 54,
            'Native proof does not cover this built ownership model')
    for name, value in proof['artifact_sha256'].items():
        require(digest(name) == value, 'Frozen native artifact changed: '+name)
    native = read(native_case/'native-3.json')
    handoff = read(native_case/'handoff-2.json')
    compatibility = read(native_case/'compat-1/native-compat-check.json')
    require(all(r.get('completed') is True and r['qemu_sha256'] == expected
                for r in (native, handoff, compatibility)), 'Native runtime gate differs')
    require(all(native.get(name) is True for name in proof['native_data_gates']), 'Native data gate is missing')
    require(handoff['retired_notifications'] == 1 and
            handoff['scheduled_old_work_and_output_backpressure_preserved'] is True and
            handoff['failed_replacement_preserves_notification_and_memory'] is True, 'Handoff gate is missing')

    live = read(case/'paired-handoff-lifecycle.json')
    inherited = read(case/'paired-ingress-lifecycle.json')
    pixels = read(case/'video-isp-lifecycle.json')
    trace = read(case/'trace.json'); lifecycle = read(case/'lifecycle.json')
    control = read(case/'statistics-control-lifecycle.json')
    status = read(case/'statistics-status-lifecycle.json')
    session = read(case/'session.json')
    require(live['build']['binary_sha256'] == inherited['build']['binary_sha256'] ==
            pixels['qemu_sha256'] == session['qemu_sha256'] == expected, 'Original-run binary identity differs')
    require(digest(case/'paired-ingress-lifecycle.json') == live['inherited_result_sha256'],
            'Inherited run record changed')
    for document in (live, inherited, pixels, control, status):
        for name, value in document['source_sha256'].items():
            require(digest(name) == value, 'Original observer source changed: '+name)
    state = assess_window(live, trace, control, minimum_seconds)
    host_profile_path = case/'paired-host-lifecycle.json'
    require(not (case/'host-timeout-lifecycle.json').exists() or host_profile_path.exists(),
            'Host diagnostic requires its explicit outer context record')
    host_profile = None
    if host_profile_path.exists():
        host_profile = read(host_profile_path)
        require(host_profile['qemu_sha256'] == expected and
                host_profile['inherited_model_record_sha256'] == digest(case/'paired-handoff-lifecycle.json') and
                host_profile['inherited_host_record_sha256'] == digest(case/'host-timeout-lifecycle.json'),
                'Host diagnostic record identity differs')
        for name, value in host_profile['source_sha256'].items():
            require(digest(name) == value, 'Host diagnostic source changed: '+name)
        for capture in host_profile['host_captures']:
            require(capture['owner']['pid'] == trace['pid'] and
                    capture['owner']['binary_sha256'] == expected, 'Debugger captured another process')
            folder = case/'host-timeout-1'
            read(folder/'capture.json')
            require(digest(folder/'host-gdb.txt') == capture['log_sha256'], 'Host stack log changed')
            if capture.get('console_available'):
                require(digest(folder/'qemu-console-tail.txt') == capture['console_tail_sha256'], 'Console tail changed')
        state = qualify_host_context(state, host_profile)
    require(allow_interrupted or state['complete'], 'Run is incomplete; use --allow-interrupted for partial evidence')
    require(all(t['control_commands_replayed'] is False for t in trace.get('observation_timeouts', [])),
            'Camera controls were replayed')
    for key in ('completed_observation', 'functional_acceptance_eligible', 'host_debugger_attached',
                'strict_mode_recovery_verified', 'video_new_pixels_reached_factory_lcd',
                'photo_return_new_pixels_reached_factory_lcd'):
        require(live[key] == inherited[key], 'Outer and inherited run verdict differ: '+key)
    if state['complete']:
        require(live['process_closed'] is True and pixels['process_closed'] is True and
                status['completed_observation'] is True, 'A complete scope has incomplete producer records')

    sources = [pixels['initial_source'], *pixels['publications']]
    for source in sources:
        payload = packet.make_packet(Image.new('RGB', (64, 64), (source['gray'],)*3),
            epoch=source['epoch'], publish_id=source['publish_id'], frame_id=source['frame_id'],
            virtual_time_ns=source['virtual_time_ns'])
        info, raw = packet.parse_packet(payload)
        require(info['raw_sha256'] == source['raw_sha256'] and
                hashlib.sha256(payload).hexdigest() == source['packet_sha256'], 'Scene packet replay differs')
        offset = 502*2272+752*3//2
        require(raw[offset:offset+48].hex() == source['raw_reference'], 'RAW reference differs')
    for row in pixels['observations']:
        path = case/row['lcd_file']
        require(path.resolve().is_relative_to(case), 'LCD file escapes its run directory')
        require(digest(path) == row['lcd_sha256'], 'Saved LCD pixels changed')
        with Image.open(path) as image:
            replay_pixel(row, image)
    before, after, photo = pixels['video_before'], pixels['video_after'], pixels['photo_after']
    video_ok = bool(before and after and before['pixel_response_verified'] and after['pixel_response_verified'] and
        before['expected_source']['gray'] == 40 and after['expected_source']['gray'] == 210 and
        after['video_batches'] > after['expected_source']['video_batches_before'])
    photo_ok = bool(photo and photo['pixel_response_verified'] and photo['expected_source']['gray'] == 40)
    require(video_ok == pixels['video_new_pixels_reached_factory_lcd'] == live['video_new_pixels_reached_factory_lcd'] and
            photo_ok == pixels['photo_return_new_pixels_reached_factory_lcd'] == live['photo_return_new_pixels_reached_factory_lcd'],
            'Scene response summary differs')
    require(live['strict_mode_recovery_verified'] == lifecycle['assessment']['recovery_observed'],
            'Original strict recovery criterion changed')
    for path in case.iterdir():
        if path.is_file() and path.suffix in ('.json', '.png', '.log', '.txt'):
            digest(path)
    for path in (__file__, host.__file__, packet.__file__, measure.__file__):
        digest(path)
    return {'schema': 1, 'version': VERSION, 'verification_completed': True,
        'native_case': str(native_case), 'run_directory': str(case), 'qemu_sha256': expected,
        'artifact_sha256': hashes, 'native_identity_verified': True,
        'completed_requested_window': state['complete'], 'functional_acceptance_eligible': state['eligible'],
        'host_context_checked': host_profile is not None,
        'host_debugger_attached': host_profile['host_debugger_attached'] if host_profile else live['host_debugger_attached'],
        'interrupted_evidence_explicitly_allowed': allow_interrupted,
        'scene_packets_replayed': len(sources), 'pixel_observations_remeasured': len(pixels['observations']),
        'video_pixels_verified_in_observed_samples': video_ok,
        'photo_pixels_verified_in_observed_samples': photo_ok,
        'video_functional_gate_passed': bool(state['eligible'] and video_ok),
        'photo_functional_gate_passed': bool(state['eligible'] and photo_ok),
        'strict_mode_recovery_verified': live['strict_mode_recovery_verified'],
        'implementation_level': 'C', 'whole_frame_pixel_identity_verified': False,
        'whole_camera_verified': False, 'physical_protocol_equivalent': False, 'camera_accessed': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native-case', type=Path, required=True)
    parser.add_argument('--run-directory', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--allow-interrupted', action='store_true')
    args = parser.parse_args()
    require(not args.output.exists(), 'Evidence output already exists')
    result = verify(args.native_case, args.run_directory, allow_interrupted=args.allow_interrupted)
    with args.output.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2)
    print(json.dumps({key: result[key] for key in ('verification_completed', 'completed_requested_window',
        'functional_acceptance_eligible', 'scene_packets_replayed', 'pixel_observations_remeasured',
        'video_functional_gate_passed', 'photo_functional_gate_passed', 'strict_mode_recovery_verified')}, indent=2), flush=True)
