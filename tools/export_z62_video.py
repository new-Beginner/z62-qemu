"""Export an owned r26 movie, independently decode it and replay its sources."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
from urllib.parse import urlsplit
from urllib.request import urlopen

from z62_directory_card import plain_path
from z62_video_card import NAME, validate_video_metadata
from z62_software_camera import Scene, SoftwareCamera
from z62_scene_packet import make_packet
from z62_video_codec import audit_video


def run(url, output, scene_path=None):
    parsed = urlsplit(url)
    if (parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or not parsed.port or
            parsed.username or parsed.path not in ('', '/') or parsed.query or parsed.fragment):
        raise ValueError('Owned numeric loopback URL required')
    output = plain_path(output)
    if output.exists():
        raise ValueError('A new export directory is required')
    plain_path(output.parent, directory=True)
    output.mkdir()
    receipt = {'completed': False, 'implementation_level': 'C', 'camera_accessed': False}
    temporary = None
    try:
        def read(path):
            with urlopen(url.rstrip('/') + path, timeout=30) as response:
                return response.read(), response.headers.get_content_type()

        state = json.loads(read('/software/status')[0])
        if state.get('video_profile') != '2026.11.01-video-console-r26b':
            raise ValueError('Expected the owned r26 video profile')
        items = [row for row in state['card']['images'] if row['kind'] == 'video']
        selected = next((row for row in items if row['name'] == state['selected_image']), items[-1] if items else None)
        if not selected or not NAME.fullmatch(selected['name']):
            raise ValueError('No finalized video is selected or available')
        data, mime = read('/software/file/' + selected['name'])
        if mime != 'video/mp4' or len(data) != selected['bytes'] or hashlib.sha256(data).hexdigest() != selected['sha256']:
            raise ValueError('Export MIME, size or hash differs from committed movie')
        metadata = selected['metadata']
        audit = validate_video_metadata(data, metadata)
        replayed = 0
        temporary = tempfile.TemporaryDirectory(prefix='z62-export-replay-')
        references = []
        for sample in metadata['samples']:
            identity = sample['scene']
            if identity['kind'] != 'chart' and scene_path is None:
                continue
            scene = (Scene(depth=identity['depth'], seed=identity['seed']) if identity['kind'] == 'chart'
                     else Scene.from_image(scene_path, depth=identity['depth']))
            camera = SoftwareCamera(scene=scene, width=sample['width'], height=sample['height'], clock_epoch=sample['clock_epoch'])
            camera.event('power', {'on': True}, 0)
            camera.lens = deepcopy(sample['lens'])
            camera.lens['moving'] = False
            camera.exposure = deepcopy(sample['exposure'])
            frame = camera.frame(sample['virtual_time_ns'])
            tag = sample['native_scene_source']
            packet = make_packet(frame.image, epoch=tag['epoch'], publish_id=tag['publish_id'],
                                 frame_id=tag['frame_id'], virtual_time_ns=tag['virtual_time_ns'])
            if frame.metadata['pixel_sha256'] != sample['pixel_sha256'] or packet[56:88].hex() != tag['raw_sha256']:
                raise ValueError('Replayed scene pixels or native RAW differ')
            reference = Path(temporary.name) / f'frame-{replayed:04d}.png'
            frame.image.save(reference, format='PNG')
            references.append(reference)
            replayed += 1
        if replayed == len(metadata['samples']):
            audit = audit_video(data, references, [row['pixel_sha256'] for row in metadata['samples']])
            if audit['max_source_mse'] > 1000:
                raise ValueError('Decoded movie differs excessively from replayed source')
        with (output / selected['name']).open('xb') as handle:
            handle.write(data)
        with (output / 'media.json').open('x', encoding='utf-8') as handle:
            json.dump(selected, handle, indent=2)
        receipt.update(completed=True, name=selected['name'], sha256=selected['sha256'], mime=mime,
            audit=audit, replayed_sources=replayed, total_sources=len(metadata['samples']),
            all_sources_replayed=replayed == len(metadata['samples']), factory_video_verified=False)
    except Exception as exc:
        receipt['failure'] = {'type': type(exc).__name__, 'message': str(exc)}
    finally:
        if temporary is not None:
            temporary.cleanup()
    with (output / 'export.json').open('x', encoding='utf-8') as handle:
        json.dump(receipt, handle, indent=2)
    print(json.dumps({key: receipt.get(key) for key in ('completed', 'replayed_sources', 'total_sources', 'failure')}, indent=2))
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--scene', type=Path)
    args = parser.parse_args()
    raise SystemExit(0 if run(args.url, args.output, args.scene)['completed'] else 1)
