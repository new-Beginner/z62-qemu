"""Owned QEMU body/RAW/JPEG flow with independent decode and source-frame replay."""
import argparse
from copy import deepcopy
import hashlib
from io import BytesIO
import json
from pathlib import Path
import shutil
import subprocess
import time
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

import numpy as np
from PIL import Image

import probe_z62_entry as entry
from z62_software_camera import SoftwareCamera, Scene
from z62_scene_packet import make_packet


def require(condition, message):
    if not condition:
        raise ValueError(message)


def exercise(http, output, receipt, observe_only=False):
    def get(path):
        result = json.loads(http(path))
        receipt['last_software_state' if path == '/software/status' else 'last_firmware_state'] = result
        return result

    def post(kind, payload):
        result = json.loads(http('/camera/event', True, {'type': kind, 'payload': payload}))
        receipt['events'].append({'type': kind, 'payload': payload})
        return result

    def wait(predicate, *, firmware=False, seconds=180):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            state = get('/status' if firmware else '/software/status')
            if predicate(state):
                return state
            time.sleep(.25)
        raise TimeoutError('Native scene/body state did not reach its requested condition')

    firmware = get('/status')
    require(firmware.get('hardware_version') == '2026.11.01-r24' and
            firmware.get('native_scene', {}).get('version') == '2026.11.01-native-scene-console-r24',
            'Target is not the owned native-scene QEMU profile')
    receipt['profile_verified'] = True
    state = wait(lambda s: s['native_scene'].get('last_consumed') is not None and
                 s['native_scene']['transport'] == 'file-mailbox')
    (output / 'software-before.jpg').write_bytes(http('/software/frame'))
    (output / 'firmware-before.png').write_bytes(http('/frame'))
    if observe_only:
        receipt['observation_completed'] = True
        return
    require(state['card']['images'] == [], 'Use a fresh dedicated card; existing photos are not modified by this probe')
    firmware = wait(lambda s: s.get('display_enabled') and
                    s.get('preview_status', {}).get('engines', {}).get('master', {}).get('preview-batches', 0) > 0,
                    firmware=True, seconds=1200)
    (output / 'firmware-ready.png').write_bytes(http('/frame'))
    post('lens', {'focus_target': .65, 'focal_length_mm': 35, 'aperture': 4})
    post('exposure', {'iso': 200, 'shutter_seconds': 1 / 125})
    settled_ns = None
    def settled(s):
        nonlocal settled_ns
        if s['lens']['moving'] or abs(s['lens']['focus_position'] - .65) > 1e-8:
            return False
        if settled_ns is None:
            settled_ns = s['virtual_time_ns']
        tag = s['native_scene'].get('last_consumed')
        return (s['native_scene']['current_settings_consumed'] and tag and
                tag['virtual_time_ns'] >= settled_ns)
    state = wait(settled)
    receipt['settled_source'] = state['native_scene']
    # Both the upper body buttons and the C pane use these exact queued edges.
    post('key', {'pin': 25, 'level': 0})
    post('key', {'pin': 25, 'level': 1})
    state = wait(lambda s: len(s['card']['images']) == 1)
    saved = state['card']['images'][0]
    jpeg = http('/software/file/' + saved['name'])
    require(hashlib.sha256(jpeg).hexdigest() == saved['sha256'], 'Stored/downloaded JPEG differs')
    path = output / 'captured.jpg'
    path.write_bytes(jpeg)
    metadata = saved['metadata']
    with Image.open(BytesIO(jpeg)) as image:
        image.load()
        require(json.loads(image.getexif()[270]) == metadata, 'EXIF source metadata differs')
    tag = metadata['native_scene_source']
    require(metadata['frame_id'] == tag['frame_id'] and metadata['virtual_time_ns'] == tag['virtual_time_ns'] and
            metadata['capture_virtual_time_ns'] >= metadata['virtual_time_ns'], 'Photo is not bound to an acknowledged RAW input')
    reference = SoftwareCamera(width=metadata['width'], height=metadata['height'], scene=Scene())
    reference.event('power', {'on': True}, 0)
    reference.lens = deepcopy(metadata['lens'])
    reference.lens['moving'] = False
    reference.exposure = deepcopy(metadata['exposure'])
    frame = reference.frame(metadata['virtual_time_ns'])
    require(frame.metadata['pixel_sha256'] == metadata['pixel_sha256'], 'Captured source cannot be replayed')
    packet = make_packet(frame.image, epoch=tag['epoch'], publish_id=tag['publish_id'],
                         frame_id=tag['frame_id'], virtual_time_ns=tag['virtual_time_ns'])
    require(packet[56:88].hex() == tag['raw_sha256'], 'Captured RGB source differs from native packed12 payload')
    ffmpeg = shutil.which('ffmpeg')
    require(ffmpeg is not None, 'Independent FFmpeg decoder is required')
    decoded = subprocess.run([ffmpeg, '-hide_banner', '-v', 'error', '-threads', '1', '-i', str(path),
                              '-f', 'rawvideo', '-pix_fmt', 'rgb24', 'pipe:1'], capture_output=True, timeout=30)
    require(decoded.returncode == 0 and len(decoded.stdout) == metadata['width'] * metadata['height'] * 3,
            'Independent JPEG decode failed')
    mse = float(np.mean((np.frombuffer(decoded.stdout, dtype=np.uint8).astype(float) - np.asarray(frame.image).reshape(-1)) ** 2))
    require(mse < 100, f'JPEG differs from the consumed input source: MSE={mse}')
    receipt.update(captured=saved, source_payload_replayed=True, independent_decode={'mse': mse, 'decoder': ffmpeg})
    (output / 'firmware-after-exposure.png').write_bytes(http('/frame'))
    post('key', {'pin': 8, 'level': 0})
    post('key', {'pin': 8, 'level': 1})
    wait(lambda s: s['view'] == 'playback')
    for _ in range(2):
        post('key', {'pin': 22, 'level': 0})
        post('key', {'pin': 22, 'level': 1})
    wait(lambda s: s['zoom'] == 4)
    (output / 'playback-zoom.jpg').write_bytes(http('/software/frame'))
    require(http('/software/file/' + saved['name']) == jpeg, 'Zoom modified the photo')
    post('key', {'pin': 23, 'level': 0})
    post('key', {'pin': 23, 'level': 1})
    wait(lambda s: s['card']['images'] == [])
    post('key', {'pin': 24, 'level': 0})
    post('key', {'pin': 24, 'level': 1})
    wait(lambda s: s['native_scene']['last_consumed'] is not None and
         s['virtual_time_ns'] - s['native_scene']['last_consumed']['virtual_time_ns'] < 200_000_000)
    receipt['final_firmware_state'] = get('/status')
    receipt.update(body_shutter_play_zoom_delete_verified=True, complete_camera_verified=False)


def run(output, url=None, firmware=None, stop=False, observe_only=False):
    if output.exists():
        raise ValueError('Probe output directory must not exist')
    receipt = {'schema': 1, 'completed': False, 'events': [], 'implementation_level': 'C',
               'factory_photo_encoding_verified': False, 'camera_accessed': False}
    try:
        if url:
            parsed = urlsplit(url)
            require(parsed.scheme == 'http' and parsed.hostname == '127.0.0.1' and parsed.port and
                    parsed.path in ('', '/') and not parsed.query and not parsed.fragment and not parsed.username,
                    'Expected the owned numeric loopback QEMU URL')
            output.mkdir(parents=True, exist_ok=False)
            def http(path, post=False, payload=None):
                request = Request(url.rstrip('/') + path, data=json.dumps(payload or {}).encode() if post else None,
                                  headers={'Content-Type': 'application/json'} if post else {})
                with urlopen(request, timeout=30) as response:
                    return response.read()
            exercise(http, output, receipt, observe_only)
            if stop:
                receipt['stop_attempted'] = True
                receipt['stop_response'] = http('/stop', True).decode()
        else:
            result = entry.run(output, expected_version='2026.10.29-no-lens-r16', diagnostic_key='preview_status',
                firmware=firmware, python_entry=entry.ROOT / 'tools/run_z62_native_scene_console.py',
                expected_hardware_version='2026.11.01-r24', require_monitor_transport=True,
                before_stop=lambda http: exercise(http, output, receipt, observe_only),
                entry_args=['--software-card', str(output.resolve() / 'card')])
            require(result['completed'] and result['process_closed'] and not result.get('forced_cleanup'),
                    'Native-scene host did not close normally')
            receipt['process_closed'] = True
        receipt['completed'] = True
    except Exception as exc:
        receipt['failure'] = {'type': type(exc).__name__, 'message': str(exc)}
    finally:
        if url and stop and receipt.get('profile_verified') and not receipt.get('stop_attempted'):
            receipt['stop_attempted'] = True
            try:
                receipt['stop_response'] = http('/stop', True).decode()
            except Exception as exc:
                receipt['stop_failure'] = {'type': type(exc).__name__, 'message': str(exc)}
        if output.is_dir():
            with (output / 'native-console-check.json').open('x', encoding='utf-8') as handle:
                json.dump(receipt, handle, indent=2)
    print(json.dumps({key: receipt.get(key) for key in ('completed', 'source_payload_replayed', 'independent_decode', 'failure')}, indent=2))
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--url')
    parser.add_argument('--firmware', type=Path)
    parser.add_argument('--stop', action='store_true')
    parser.add_argument('--observe-only', action='store_true')
    args = parser.parse_args()
    raise SystemExit(0 if run(args.output, args.url, args.firmware, args.stop, args.observe_only)['completed'] else 1)
