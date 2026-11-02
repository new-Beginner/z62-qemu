"""Actual QEMU HTTP software-photo flow and independent FFmpeg JPEG decode."""
import argparse
import hashlib
from io import BytesIO
import json
from pathlib import Path
import shutil
import subprocess
import time

import numpy as np
from PIL import Image

import probe_z62_entry as entry
from z62_directory_card import DirectoryCard
from z62_software_camera import Scene, SoftwareCamera


def require(condition, message):
    if not condition:
        raise ValueError(message)


def run(output, firmware=None):
    receipt = {'schema': 1, 'completed': False, 'implementation_level': 'C',
               'factory_capture_chain_verified': False, 'nef_verified': False,
               'video_verified': False, 'camera_accessed': False, 'events': []}
    ffmpeg = shutil.which('ffmpeg')
    require(ffmpeg is not None, 'FFmpeg is required for an independent JPEG decoder')

    def checks(http):
        def get(path):
            return json.loads(http(path))

        def event(kind, payload):
            result = json.loads(http('/software/event', True, {'type': kind, 'payload': payload}))
            receipt['events'].append({'type': kind, 'payload': payload,
                                      'virtual_time_ns': result['state']['virtual_time_ns']})
            return result

        initial = get('/software/status')
        require(initial['implementation_level'] == 'C' and not initial['powered']
                and initial['card']['images'] == [], 'Expected a new, powered-off software camera')
        event('power', {'on': True})
        event('lens', {'focus_target': .65, 'focal_length_mm': 35, 'aperture': 4})
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            state = get('/software/status')
            if not state['lens']['moving'] and abs(state['lens']['focus_position'] - .65) < 1e-8:
                break
            time.sleep(.15)
        else:
            raise TimeoutError('Lens did not reach its manual target in QEMU virtual time')
        (output / 'focused-preview.jpg').write_bytes(http('/software/frame'))
        event('exposure', {'iso': 200, 'shutter_seconds': 1 / 125})
        before = get('/software/status')['virtual_time_ns']
        try:
            saved = event('shutter', {'stage': 'full', 'pressed': True})['result']
        finally:
            event('shutter', {'stage': 'full', 'pressed': False})
        raw = http('/software/file/' + saved['name'])
        require(hashlib.sha256(raw).hexdigest() == saved['sha256'], 'Downloaded photo differs from committed JPEG')
        path = output / 'captured.jpg'
        path.write_bytes(raw)
        with Image.open(BytesIO(raw)) as image:
            image.load()
            metadata = json.loads(image.getexif()[270])
            require(metadata == saved['metadata'], 'EXIF capture state differs from card catalog')
        require(metadata['virtual_time_ns'] >= before and metadata['frame_id'] == metadata['virtual_time_ns'] * 30 // 1_000_000_000,
                'Capture does not share the QEMU frame/time domain')
        decoded = subprocess.run([ffmpeg, '-hide_banner', '-v', 'error', '-threads', '1',
            '-i', str(path), '-f', 'rawvideo', '-pix_fmt', 'rgb24', 'pipe:1'], capture_output=True, timeout=30)
        require(decoded.returncode == 0, 'Independent decode failed: ' + decoded.stderr.decode(errors='replace'))
        expected_size = metadata['width'] * metadata['height'] * 3
        require(len(decoded.stdout) == expected_size, 'Independent decoded dimensions differ')
        reference = SoftwareCamera(width=metadata['width'], height=metadata['height'], scene=Scene(),
                                   clock_epoch=metadata['clock_epoch'])
        reference.event('power', {'on': True}, 0)
        reference.event('lens', {'focus_target': .65, 'focal_length_mm': 35, 'aperture': 4}, 0)
        reference.event('exposure', metadata['exposure'], 0)
        expected = reference.frame(metadata['virtual_time_ns'])
        require(expected.metadata['pixel_sha256'] == metadata['pixel_sha256'], 'Photo source cannot be replayed from captured state')
        difference = np.frombuffer(decoded.stdout, dtype=np.uint8).astype(float) - np.asarray(expected.image).reshape(-1)
        mse = float(np.mean(difference ** 2))
        require(mse < 100, f'Independent decoded photo is inconsistent with the current scene: MSE={mse}')
        receipt['independent_decode'] = {'decoder': ffmpeg, 'rgb_bytes': expected_size,
                                         'mse_vs_rendered_capture': mse, 'jpeg_sha256': saved['sha256']}
        event('playback', {'action': 'open'})
        full = http('/software/frame')
        event('zoom', {'factor': 4})
        zoomed = http('/software/frame')
        (output / 'playback-zoom.jpg').write_bytes(zoomed)
        require(full != zoomed and http('/software/file/' + saved['name']) == raw,
                'Playback zoom failed or modified the stored photo')
        event('playback', {'action': 'close'})
        event('exposure', {'iso': 400})
        try:
            second = event('shutter', {'stage': 'full', 'pressed': True})['result']
        finally:
            event('shutter', {'stage': 'full', 'pressed': False})
        require(second['name'] == 'Z62_0002.JPG' and len(get('/software/status')['card']['images']) == 2,
                'Second capture numbering or card list differs')
        event('playback', {'action': 'open'})
        deleted = event('delete', {})
        require(deleted['result']['deleted'] == second['name'] and
                [row['name'] for row in deleted['state']['card']['images']] == [saved['name']], 'Delete did not update the committed card')
        event('power', {'on': False})
        receipt.update(captured=saved, deleted=second['name'], playback_zoom_verified=True,
                       guest_clock_verified=True, software_state=get('/software/status'))

    try:
        result = entry.run(output, expected_version='2026.10.29-no-lens-r16', diagnostic_key='preview_status',
            firmware=firmware, python_entry=entry.ROOT / 'tools/run_z62_software_console.py',
            expected_hardware_version='2026.10.30-r21', require_monitor_transport=True,
            exercise_capture_input=True, before_stop=checks,
            entry_args=['--software-card', str(output.resolve() / 'card')])
        require(result['completed'] and result['process_closed'] and not result.get('forced_cleanup'), 'Host did not close normally')
        with DirectoryCard(output / 'card') as card:
            rows = card.list()
            require([row['name'] for row in rows] == ['Z62_0001.JPG'] and
                    card.read(rows[0]['name']) == (output / 'captured.jpg').read_bytes(),
                    'Committed card did not survive host shutdown/reopen')
        receipt.update(completed=True, clean_card_reopen_verified=True)
    except Exception as exc:
        receipt['failure'] = {'type': type(exc).__name__, 'message': str(exc)}
    finally:
        if output.is_dir():
            with (output / 'software-check.json').open('x', encoding='utf-8') as handle:
                json.dump(receipt, handle, indent=2)
    print(json.dumps({key: receipt.get(key) for key in ('completed', 'independent_decode', 'failure')}, indent=2))
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--firmware', type=Path)
    args = parser.parse_args()
    raise SystemExit(0 if run(args.output, args.firmware)['completed'] else 1)
