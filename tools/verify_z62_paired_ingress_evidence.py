"""Verify the bound C build and measured native data proof; not camera acceptance."""
import argparse
import hashlib
import json
from pathlib import Path
from PIL import Image
import run_z62_paired_ingress as host
import z62_scene_packet as packet
import z62_scene_response as measure


def require(value, message):
    if not value:
        raise ValueError(message)


def verify(directory):
    directory = directory.resolve()
    hashes = {}
    def digest(path):
        value = hashlib.sha256(path.read_bytes()).hexdigest()
        hashes[str(path)] = value
        return value
    def read(path):
        digest(path)
        return json.loads(path.read_text(encoding='utf-8'))
    build = host.verify_build()
    native = read(directory/'native-3.json')
    compat_root = directory/'compat-1'
    compat = read(compat_root/'native-compat-check.json')
    expected = build['binary_sha256']
    require(native['completed'] is True and compat['completed'] is True and
            native['qemu_sha256'] == compat['qemu_sha256'] == expected, 'Native binary identity/gate differs')
    probe = Path(__file__).with_name('probe_z62_paired_ingress.py')
    require(digest(probe) == native['probe_sha256'], 'Native proof refers to another probe source')
    gates = ('default_off', 'actual_source_bytes', 'actual_main_work_preview_oracle',
             'raw_port_remained_stopped', 'source_tags_verified', 'backpressure', 'stop',
             'explicit_paired_restart', 'slave_isolation', 'reset', 'late_invalid_no_partial_dma',
             'alias_rejected', 'active_legacy_raw_excludes_software_source',
             'second_distinct_scene_raw_main_work_preview_verified', 'legacy_actual_dma_with_option_on')
    require(all(native.get(k) is True for k in gates), 'Missing actual data/lifecycle gate')
    require(len(native['launches']) == 3 and all(r.get('process_closed') is True and r.get('exit_code') == 0
                                               for r in native['launches']), 'Native process was not closed normally')
    for row in native['launches']:
        require(digest(Path(row['log'])) == row['log_sha256'], 'Native console log changed')
    require('nikon-z72-boot-config.z62-paired-ingress=on' not in native['launches'][0]['command'] and
            all('nikon-z72-boot-config.z62-paired-ingress=on' in r['command'] for r in native['launches'][1:]),
            'Source option did not have an explicit default-off control')
    require(compat['stop_option_on'] is True, 'Compatibility suite omitted legacy stop option')
    for row in compat['logs']:
        require(digest(compat_root/row['file']) == row['sha256'], 'Compatibility trace changed')
        require(not any('z62-paired-ingress=' in v for v in row['command']),
                'Default-off compatibility was run with the new input option')
    root = host.DEFAULT_QEMU.parent.parent
    current = read(root/'reference-build-manifest.json')
    previous = read(host.parent.DEFAULT_QEMU.parent.parent/'reference-build-manifest.json')
    before, after = previous['prepared_source_file_sha256'], current['prepared_source_file_sha256']
    changed = sorted(n for n in set(before)|set(after) if before.get(n) != after.get(n))
    require(changed == sorted(build['generated_source_sha256']), 'Unaccounted source delta')
    digest(root/'paired-ingress-build-manifest.json')
    for path in (Path(__file__), Path(host.__file__), Path(host.device.__file__), *host.device.HEADERS.values()):
        digest(path)
    result = {'schema': 1, 'completed_verification': True, 'qemu_sha256': expected,
        'artifact_sha256': hashes, 'prepared_source_delta': changed, 'native_data_gates': list(gates),
        'vmstate_version': 53, 'implementation_level': 'C', 'old_raw_port_not_rearmed': True,
        'input_source_itself_emits_completion': False, 'new_statistics_source': False,
        'original_firmware_recovery_verified_by_native_tests': False,
        'physical_protocol_equivalent': False, 'camera_accessed': False}
    live_path = directory/'live-1/paired-ingress-lifecycle.json'
    if live_path.exists():
        live = read(live_path)
        require(live['build']['binary_sha256'] == expected, 'Original-firmware observation used another binary')
        for name, value in live['source_sha256'].items():
            require(digest(Path(name)) == value, 'Live observer source changed')
        case = live_path.parent
        pixels = read(case/'video-isp-lifecycle.json')
        trace = read(case/'trace.json')
        lifecycle = read(case/'lifecycle.json')
        require(pixels['qemu_sha256'] == expected and pixels['process_closed'] is True and
                trace['process_closed'] is True and trace['detach'] == 'OK' and
                not trace.get('failure') and not trace.get('cleanup_error'), 'Original window did not close normally')
        for name, value in pixels['source_sha256'].items():
            require(digest(Path(name)) == value, 'Pixel observer source changed')
        sources = [pixels['initial_source'], *pixels['publications']]
        for source in sources:
            payload = packet.make_packet(Image.new('RGB', (64, 64), (source['gray'],)*3),
                epoch=source['epoch'], publish_id=source['publish_id'], frame_id=source['frame_id'],
                virtual_time_ns=source['virtual_time_ns'])
            info, raw = packet.parse_packet(payload)
            require(info['raw_sha256'] == source['raw_sha256'] and
                    hashlib.sha256(payload).hexdigest() == source['packet_sha256'], 'Scene packet replay differs')
            offset = 502*2272+752*3//2
            require(raw[offset:offset+48].hex() == source['raw_reference'], 'Scene reference differs')
        for row in pixels['observations']:
            png = case/row['lcd_file']; source = row['expected_source']
            require(digest(png) == row['lcd_sha256'], 'Saved factory LCD changed')
            with Image.open(png) as image:
                actual = measure.measure(source['gray'], bytes.fromhex(source['raw_reference']),
                    [bytes.fromhex(p) for p in row['raw_patches']],
                    [{'y': bytes.fromhex(p['y']), 'uv': bytes.fromhex(p['uv'])} for p in row['nv12_patches']], image)
            require(actual == row['measure'], 'Pixel measurement replay differs')
            tags = {'scene-used-publish-id': 'publish_id', 'scene-used-epoch': 'epoch',
                    'scene-used-frame-id': 'frame_id', 'scene-used-time-ns': 'virtual_time_ns'}
            tag_match = all(row['source'][key] == source[name] for key, name in tags.items())
            mode_match = row['mode_heights'][1] == 576 if row['kind'].startswith('video') else row['mode_heights'][1] in (680, 682)
            response = bool(tag_match and mode_match and row['display_enabled'] and row['index'] == 3 and
                            all(actual[k] for k in ('raw_matches', 'nv12_matches', 'lcd_matches')))
            require(response == row['pixel_response_verified'], 'Pixel response verdict differs')
        before, after, photo = pixels['video_before'], pixels['video_after'], pixels['photo_after']
        video_ok = bool(before and after and before['pixel_response_verified'] and after['pixel_response_verified'] and
                        before['expected_source']['gray'] == 40 and after['expected_source']['gray'] == 210 and
                        after['video_batches'] > after['expected_source']['video_batches_before'])
        photo_ok = bool(photo and photo['pixel_response_verified'] and photo['expected_source']['gray'] == 40)
        require(video_ok == live['video_new_pixels_reached_factory_lcd'] == pixels['video_new_pixels_reached_factory_lcd'] and
                photo_ok == live['photo_return_new_pixels_reached_factory_lcd'] == pixels['photo_return_new_pixels_reached_factory_lcd'],
                'Factory scene verdict differs')
        require(live['strict_mode_recovery_verified'] == lifecycle['assessment']['recovery_observed'], 'Strict criterion was changed')
        require(all(row['control_commands_replayed'] is False for row in trace.get('observation_timeouts', [])),
                'Camera controls were replayed')
        result['scene_packets_replayed'] = len(sources)
        result['pixel_observations_remeasured'] = len(pixels['observations'])
        result['whole_frame_pixel_identity_verified'] = False
        for path in case.glob('*'):
            if path.is_file() and path.suffix in ('.json', '.png', '.log', '.txt'):
                digest(path)
        result['original_firmware_observation'] = {k: live[k] for k in
            ('completed_observation', 'process_closed', 'functional_acceptance_eligible', 'host_debugger_attached',
             'strict_mode_recovery_verified', 'video_new_pixels_reached_factory_lcd',
             'photo_return_new_pixels_reached_factory_lcd')}
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError('Verification evidence is immutable')
    result = verify(args.directory)
    with args.output.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2)
    print(json.dumps({'completed_verification': True, 'qemu_sha256': result['qemu_sha256'],
        'artifact_count': len(result['artifact_sha256']), 'native_gates': len(result['native_data_gates']),
        'original_firmware_observation': result.get('original_firmware_observation')}, indent=2), flush=True)
