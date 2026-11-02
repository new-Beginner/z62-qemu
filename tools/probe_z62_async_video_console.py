"""Real QEMU r27 encoding/cancel/close with live-handle and responsiveness evidence."""
import argparse
import hashlib
from io import BytesIO
import json
from pathlib import Path
import tempfile
import time

from PIL import Image

import probe_z62_entry as entry
from probe_z62_native_scene_console import require
from probe_z62_video_console import replay_sample
from z62_async_video_card import AsyncVideoCard
from z62_video_card import validate_video_metadata
from z62_video_codec import audit_video
from z62_scene_packet import make_packet

ROOT = Path(__file__).resolve().parents[1]


def run(output, firmware=None, scenario='encode', frames=120):
    receipt = {'schema': 1, 'completed': False, 'implementation_level': 'C', 'scenario': scenario,
               'events': [], 'observations': [], 'requests': [], 'factory_video_verified': False,
               'camera_accessed': False}

    def checks(http):
        def request(path, post=False, payload=None):
            started = time.monotonic()
            data = http(path, post, payload)
            receipt['requests'].append({'path': path, 'seconds': time.monotonic() - started})
            return data

        def get(path='/software/status'):
            return json.loads(request(path))

        def post(kind, payload):
            value = json.loads(request('/camera/event', True, {'type': kind, 'payload': payload}))
            receipt['events'].append({'type': kind, 'payload': payload})
            return value

        def wait(predicate, *, firmware=False, seconds=180):
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                state = get('/status' if firmware else '/software/status')
                if predicate(state):
                    return state
                if state.get('video', {}).get('terminal') and state['video']['phase'] == 'error':
                    raise ValueError('Actual async video error: ' + str(state['video']['error']))
                time.sleep(.15)
            raise TimeoutError('r27 state condition was not reached')

        state = get()
        require(state.get('video_profile') == '2026.11.01-async-video-console-r27' and
                state['capabilities']['async_video'] and state['card']['images'] == [], 'Fresh r27 card/profile required')
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
        wait(lambda s: s['video']['frames'] >= frames)
        started = time.monotonic()
        post('record', {'action': 'stop'})
        receipt['stop_post_seconds'] = time.monotonic() - started
        state = wait(lambda s: s['video'].get('worker_running') and not s['video'].get('terminal'))
        require(state['card']['videos'] == 0, 'A live worker was prematurely reported as saved')
        receipt['live_worker_pid'] = state['video']['worker_pid']
        receipt['live_job_directory'] = state['video']['job_directory']

        def observe(state):
            firmware_state = get('/status')
            video = state['video']
            row = {'virtual_time_ns': state['virtual_time_ns'], 'phase': video['phase'],
                   'worker_pid': video['worker_pid'], 'worker_running': video['worker_running'],
                   'terminal': video['terminal'], 'saved_videos': state['card']['videos'],
                   'preview_batches': firmware_state.get('preview_status', {}).get('engines', {}).get('master', {}).get('preview-batches'),
                   'source_publish_id': state['native_scene'].get('last_consumed', {}).get('publish_id')}
            receipt['observations'].append(row)

        observe(state)
        post('heartbeat', {})
        if scenario == 'close':
            receipt['close_requested_while_worker_confirmed_live'] = True
            return  # The owning entry helper now closes the host normally.
        if scenario == 'cancel':
            started = time.monotonic()
            post('record', {'action': 'cancel'})
            receipt['cancel_post_seconds'] = time.monotonic() - started
            state = wait(lambda s: s['video'].get('terminal'))
            require(state['video']['phase'] == 'cancelled' and state['card']['images'] == [] and
                    not state['video']['worker_running'], 'Cancellation did not confirm worker exit/no publication')
            receipt['cancelled_without_media'] = True
            return
        deadline = time.monotonic() + 300
        while not state['video'].get('terminal') and time.monotonic() < deadline:
            state = get()
            observe(state)
            time.sleep(.15)
        require(state['video'].get('terminal') and state['video']['phase'] == 'saved',
                'Async worker did not produce a verified committed movie')
        live = [row for row in receipt['observations'] if row['worker_running']]
        require(live and any(row['virtual_time_ns'] > live[0]['virtual_time_ns'] for row in live[1:]),
                'Did not observe guest time advancing while the worker was live')
        require(any(row['preview_batches'] > live[0]['preview_batches'] for row in live[1:]),
                'Native preview did not advance during background encoding')
        receipt['guest_and_preview_advanced_during_job'] = True
        summary = state['card']['images'][0]
        require('samples' not in summary['metadata'], 'Status leaked the complete per-frame catalog')
        item = get(summary['detail_url'])
        video = request('/software/file/' + item['name'])
        require(hashlib.sha256(video).hexdigest() == item['sha256'], 'Downloaded video differs from committed file')
        metadata = item['metadata']
        validate_video_metadata(video, metadata)
        with tempfile.TemporaryDirectory(prefix='z62-async-source-') as directory:
            references = []
            for index, sample in enumerate(metadata['samples']):
                frame = replay_sample(sample)
                tag = sample['native_scene_source']
                packet = make_packet(frame.image, epoch=tag['epoch'], publish_id=tag['publish_id'],
                                     frame_id=tag['frame_id'], virtual_time_ns=tag['virtual_time_ns'])
                require(frame.metadata['pixel_sha256'] == sample['pixel_sha256'] and packet[56:88].hex() == tag['raw_sha256'],
                        'Replayed source differs from acknowledged RAW')
                path = Path(directory) / f'frame-{index:04d}.png'
                frame.image.save(path, format='PNG')
                references.append(path)
            audit = audit_video(video, references, [row['pixel_sha256'] for row in metadata['samples']])
        require(audit['timestamps_us'] == metadata['timestamps_us'] and audit['duration_us'] == metadata['duration_us'] and
                audit['max_source_mse'] <= 1000, 'Independent async movie audit differs')
        (output / 'actual.mp4').write_bytes(video)
        receipt.update(saved=item, independent_audit=audit, all_sources_replayed=True)
        post('playback', {'action': 'open'})
        wait(lambda s: s.get('selected_media_kind') == 'video')
        with Image.open(BytesIO(request('/software/frame'))) as poster:
            poster.load()
            require(poster.size == (metadata['width'], metadata['height']), 'Poster geometry differs')
        post('delete', {})
        wait(lambda s: s['card']['images'] == [])
        receipt['playback_delete_verified'] = True

    try:
        result = entry.run(output, expected_version='2026.10.29-no-lens-r16', diagnostic_key='preview_status',
            firmware=firmware, python_entry=ROOT / 'tools/run_z62_async_video_console.py',
            expected_hardware_version='2026.11.01-r24', require_monitor_transport=True,
            before_stop=checks, entry_args=['--software-card', str(output.resolve() / 'card')])
        require(result['completed'] and result['process_closed'] and not result.get('forced_cleanup'), 'Async host did not close normally')
        with AsyncVideoCard(output / 'card') as card:
            require(card.list() == [], 'Media appeared or reappeared after host closure')
        if scenario == 'close':
            parent_result = json.loads((Path(receipt['live_job_directory']) / 'parent-result.json').read_bytes())
            require(parent_result['phase'] == 'cancelled' and parent_result['worker_exit_code'] is not None and
                    not parent_result['worker_running'], 'Closing did not stop its owned worker')
        receipt.update(completed=True, process_closed=True, empty_card_reopened=True)
    except Exception as exc:
        receipt['failure'] = {'type': type(exc).__name__, 'message': str(exc)}
    finally:
        if output.is_dir():
            with (output / 'async-video-check.json').open('x', encoding='utf-8') as handle:
                json.dump(receipt, handle, indent=2)
    print(json.dumps({key: receipt.get(key) for key in ('completed', 'scenario', 'stop_post_seconds', 'failure')}, indent=2))
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--firmware', type=Path)
    parser.add_argument('--scenario', choices=('encode', 'cancel', 'close'), default='encode')
    parser.add_argument('--frames', type=int, default=120)
    args = parser.parse_args()
    if not 20 <= args.frames <= 300:
        parser.error('frames must be in 20..300')
    raise SystemExit(0 if run(args.output, args.firmware, args.scenario, args.frames)['completed'] else 1)
