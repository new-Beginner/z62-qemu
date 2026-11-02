"""Read-only r27 video export with explicit full metadata and source replay."""
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
from z62_video_codec import audit_video
from z62_software_camera import Scene, SoftwareCamera
from z62_scene_packet import make_packet


def run(url, output, scene_path=None):
    parsed = urlsplit(url)
    if (parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or not parsed.port or
            parsed.username or parsed.path not in ('', '/') or parsed.query or parsed.fragment):
        raise ValueError('Owned numeric loopback URL required')
    output = plain_path(output)
    if output.exists():
        raise ValueError('Fresh export directory required')
    plain_path(output.parent, directory=True)
    output.mkdir()
    receipt = {'schema': 1, 'completed': False, 'implementation_level': 'C', 'camera_accessed': False}
    try:
        def read(path):
            with urlopen(url.rstrip('/') + path, timeout=30) as response:
                return response.read(), response.headers.get_content_type()

        state = json.loads(read('/software/status')[0])
        if state.get('video_profile') != '2026.11.01-async-video-console-r27':
            raise ValueError('Owned r27 profile required')
        videos = [row for row in state['card']['images'] if row['kind'] == 'video']
        item = next((row for row in videos if row['name'] == state['selected_image']), videos[-1] if videos else None)
        if not item or not NAME.fullmatch(item['name']):
            raise ValueError('No finalized video available')
        item = json.loads(read('/software/item/' + item['name'])[0])
        data, mime = read('/software/file/' + item['name'])
        if mime != 'video/mp4' or len(data) != item['bytes'] or hashlib.sha256(data).hexdigest() != item['sha256']:
            raise ValueError('Downloaded movie differs from catalog')
        metadata = item['metadata']
        audit = validate_video_metadata(data, metadata)
        count = 0
        with tempfile.TemporaryDirectory(prefix='z62-r27-export-') as directory:
            references = []
            for index, sample in enumerate(metadata['samples']):
                identity = sample['scene']
                if identity['kind'] != 'chart' and scene_path is None:
                    continue
                scene = (Scene(depth=identity['depth'], seed=identity['seed']) if identity['kind'] == 'chart'
                         else Scene.from_image(scene_path, depth=identity['depth']))
                camera = SoftwareCamera(scene=scene, width=sample['width'], height=sample['height'],
                                        clock_epoch=sample['clock_epoch'])
                camera.event('power', {'on': True}, 0)
                camera.lens = deepcopy(sample['lens'])
                camera.lens['moving'] = False
                camera.exposure = deepcopy(sample['exposure'])
                frame = camera.frame(sample['virtual_time_ns'])
                tag = sample['native_scene_source']
                packet = make_packet(frame.image, epoch=tag['epoch'], publish_id=tag['publish_id'],
                                     frame_id=tag['frame_id'], virtual_time_ns=tag['virtual_time_ns'])
                if frame.metadata['pixel_sha256'] != sample['pixel_sha256'] or packet[56:88].hex() != tag['raw_sha256']:
                    raise ValueError('Replayed source differs from acknowledged RGB/RAW')
                path = Path(directory) / f'frame-{index:04d}.png'
                frame.image.save(path, format='PNG')
                references.append(path)
                count += 1
            if count == len(metadata['samples']):
                audit = audit_video(data, references, [row['pixel_sha256'] for row in metadata['samples']])
                if audit['max_source_mse'] > 1000:
                    raise ValueError('Movie/source image error exceeds experimental limit')
        with (output / item['name']).open('xb') as handle:
            handle.write(data)
        with (output / 'media.json').open('x', encoding='utf-8') as handle:
            json.dump(item, handle, indent=2)
        receipt.update(completed=True, name=item['name'], sha256=item['sha256'], mime=mime, audit=audit,
                       replayed_sources=count, total_sources=len(metadata['samples']),
                       all_sources_replayed=count == len(metadata['samples']), factory_video_verified=False)
    except Exception as exc:
        receipt['failure'] = {'type': type(exc).__name__, 'message': str(exc)}
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
