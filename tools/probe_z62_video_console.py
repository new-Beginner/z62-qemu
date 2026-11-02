"""Actual QEMU video flow; replay every source and independently decode MP4."""
import argparse
from copy import deepcopy
import hashlib
from io import BytesIO
import json
from pathlib import Path
import time
import tempfile

from PIL import Image

import probe_z62_entry as entry
from probe_z62_native_scene_console import require
from z62_software_camera import SoftwareCamera, Scene
from z62_scene_packet import make_packet
from z62_video_codec import audit_video
from z62_video_card import VideoCard

ROOT = Path(__file__).resolve().parents[1]


def replay_sample(sample):
    camera = SoftwareCamera(width=sample['width'], height=sample['height'], scene=Scene(),
                            clock_epoch=sample['clock_epoch'])
    camera.event('power', {'on': True}, 0)
    camera.lens = deepcopy(sample['lens'])
    camera.lens['moving'] = False
    camera.exposure = deepcopy(sample['exposure'])
    return camera.frame(sample['virtual_time_ns'])


def run(output, firmware=None):
    receipt = {'schema': 1, 'completed': False, 'events': [], 'implementation_level': 'C',
               'factory_video_verified': False, 'audio': False, 'camera_accessed': False}

    def checks(http):
        def get(path):
            value = json.loads(http(path))
            receipt['last_state' if path == '/software/status' else 'firmware_state'] = value
            return value

        def post(kind, payload):
            result = json.loads(http('/camera/event', True, {'type': kind, 'payload': payload}))
            receipt['events'].append({'type': kind, 'payload': payload})
            return result

        def wait(predicate, firmware=False, seconds=180):
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                state = get('/status' if firmware else '/software/status')
                if state.get('video', {}).get('phase') == 'error':
                    raise ValueError('Actual video backend error: ' + str(state['video']['error']))
                if predicate(state):
                    return state
                time.sleep(.2)
            raise TimeoutError('Actual QEMU video state did not reach its condition')

        state = get('/software/status')
        require(state.get('video_profile') == '2026.11.01-video-console-r26b' and
                state['capabilities']['video'] and state['card']['images'] == [], 'Fresh r26 video profile required')
        wait(lambda s: s.get('display_enabled') and
             s.get('preview_status', {}).get('engines', {}).get('master', {}).get('preview-batches', 0) > 0,
             firmware=True, seconds=1200)
        post('lens', {'focus_target': .65})
        wait(lambda s: not s['lens']['moving'])
        post('mode', {'mode': 'video'})
        wait(lambda s: s['native_scene']['current_settings_consumed'])
        post('record', {'action': 'start'})
        wait(lambda s: s['video']['recording'] and s['video']['frames'] >= 4)
        post('exposure', {'iso': 200})
        wait(lambda s: s['video']['frames'] >= 10)
        post('record', {'action': 'stop'})
        state = wait(lambda s: s['video']['phase'] == 'saved' and s['card']['videos'] == 1, seconds=300)
        item = state['card']['images'][0]
        data = http('/software/file/' + item['name'])
        require(hashlib.sha256(data).hexdigest() == item['sha256'], 'Downloaded movie differs from committed bytes')
        (output / 'actual.mp4').write_bytes(data)
        audit = audit_video(data)
        meta = item['metadata']
        require(audit['timestamps_us'] == meta['timestamps_us'] and audit['duration_us'] == meta['duration_us'],
                'Independent timing differs from the source timeline')
        require(len(audit['pixel_sha256']) == len(meta['samples']), 'Video frame count differs')
        raw_tags = []
        for index, sample in enumerate(meta['samples']):
            source = replay_sample(sample)
            require(source.metadata['pixel_sha256'] == sample['pixel_sha256'],
                    'An input movie frame does not match its replayed scene')
            tag = sample['native_scene_source']
            packet = make_packet(source.image, epoch=tag['epoch'], publish_id=tag['publish_id'],
                                 frame_id=tag['frame_id'], virtual_time_ns=tag['virtual_time_ns'])
            require(packet[56:88].hex() == tag['raw_sha256'], 'Movie frame differs from acknowledged native RAW')
            raw_tags.append(tag['publish_id'])
        with tempfile.TemporaryDirectory(prefix='z62-replay-') as reference_directory:
            references = []
            for index, sample in enumerate(meta['samples']):
                source = replay_sample(sample)
                path = Path(reference_directory) / f'frame-{index:04d}.png'
                source.image.save(path, format='PNG')
                references.append(path)
            audit = audit_video(data, references, [row['pixel_sha256'] for row in meta['samples']])
        require(audit['pixel_format'] == 'yuv420p' and audit['max_source_mse'] <= 1000,
                'Browser-compatible movie does not match its replayed source quality')
        require(audit['pixel_sha256'] == meta['encoded_pixel_sha256'], 'Stored decoded-frame hashes differ')
        require(len(set(raw_tags)) == len(raw_tags), 'A repeated publication was fabricated as a new frame')
        require(len(set(audit['pixel_sha256'])) > 1, 'Movie did not contain changing scene/exposure pixels')
        receipt.update(saved=item, independent_audit=audit, all_sources_replayed=True)
        post('playback', {'action': 'open'})
        wait(lambda s: s.get('selected_media_kind') == 'video')
        poster = http('/software/frame')
        with Image.open(BytesIO(poster)) as image:
            image.load()
            require(image.size == (meta['width'], meta['height']), 'Video poster geometry differs')
        (output / 'video-poster.jpg').write_bytes(poster)
        post('delete', {})
        wait(lambda s: s['card']['images'] == [] and s['card']['videos'] == 0)
        receipt['playback_and_group_delete_verified'] = True

    try:
        result = entry.run(output, expected_version='2026.10.29-no-lens-r16', diagnostic_key='preview_status',
            firmware=firmware, python_entry=ROOT / 'tools/run_z62_video_console.py',
            expected_hardware_version='2026.11.01-r24', require_monitor_transport=True,
            before_stop=checks, entry_args=['--software-card', str(output.resolve() / 'card')])
        require(result['completed'] and result['process_closed'] and not result.get('forced_cleanup'),
                'Video host did not close normally')
        with VideoCard(output / 'card') as card:
            require(card.list() == [], 'Deleted movie reappeared after shutdown')
        receipt.update(completed=True, process_closed=True, empty_card_reopened=True)
    except Exception as exc:
        receipt['failure'] = {'type': type(exc).__name__, 'message': str(exc)}
    finally:
        if output.is_dir():
            with (output / 'video-check.json').open('x', encoding='utf-8') as handle:
                json.dump(receipt, handle, indent=2)
    print(json.dumps({key: receipt.get(key) for key in ('completed', 'all_sources_replayed', 'failure')}, indent=2))
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--firmware', type=Path)
    args = parser.parse_args()
    raise SystemExit(0 if run(args.output, args.firmware)['completed'] else 1)
