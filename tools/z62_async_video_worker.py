"""Owned child: preserve source evidence, encode, independently validate, then exit."""
import argparse
from io import BytesIO
import json
from pathlib import Path
import sys
import time

from PIL import Image

try:
    from .z62_async_video_job import VERSION, atomic_json, canonical, code_hashes, digest
    from .z62_directory_card import plain_path
    from .z62_video_codec import VideoRecorder
    from .z62_video_card import validate_video_metadata
    from .z62_software_camera import Frame
except ImportError:
    from z62_async_video_job import VERSION, atomic_json, canonical, code_hashes, digest
    from z62_directory_card import plain_path
    from z62_video_codec import VideoRecorder
    from z62_video_card import validate_video_metadata
    from z62_software_camera import Frame


def run(directory):
    directory = plain_path(directory, directory=True)
    raw = plain_path(directory / 'descriptor.json', directory=False).read_bytes()
    if len(raw) > 32 * 1024 * 1024:
        raise ValueError('video_job_descriptor_size')
    job = json.loads(raw)
    prepared = 0
    recorder = None

    def progress(phase):
        atomic_json(directory / 'progress.json', {'job_id': job['job_id'], 'phase': phase, 'prepared_frames': prepared})

    try:
        if (job['version'] != VERSION or code_hashes() != job['code_sha256'] or
                digest(plain_path(Path(sys.argv[0]), directory=False).read_bytes()) != job['entry_sha256'] or
                digest(canonical(job['samples'])) != job['source_map_sha256'] or not 2 <= len(job['samples']) <= 1800):
            raise ValueError('video_worker_input_identity')
        deadline = time.monotonic() + 10
        while not (directory / 'contained.json').exists():
            if time.monotonic() > deadline:
                raise TimeoutError('video_worker_parent_containment_missing')
            time.sleep(.02)
        if json.loads((directory / 'contained.json').read_bytes())['job_id'] != job['job_id']:
            raise ValueError('video_worker_containment_identity')
        source = plain_path(job['source_directory'], directory=True)
        archive = directory / 'input'
        archive.mkdir()
        output = directory / 'output'
        output.mkdir()
        recorder = VideoRecorder(directory / 'scratch', start_ns=job['start_ns'], clock_epoch=job['clock_epoch'])
        progress('preparing')
        for index, metadata in enumerate(job['samples']):
            path = plain_path(source / f'frame-{index:04d}.png', directory=False)
            with Image.open(path) as image:
                image.load()
                image = image.convert('RGB')
            if image.size != (metadata['width'], metadata['height']) or digest(image.tobytes()) != metadata['pixel_sha256']:
                raise ValueError('video_worker_source_pixels_changed')
            with (archive / path.name).open('xb') as handle:
                image.save(handle, format='PNG')
            recorder.append(Frame(image, metadata))
            prepared += 1
            progress('preparing')
        progress('encoding_auditing')
        media = recorder.finish(job['stop_ns'])
        progress('validating')
        validate_video_metadata(media['video'], media['metadata'])
        with Image.open(BytesIO(media['poster'])) as poster:
            poster.load()
            if poster.format != 'JPEG' or poster.size != (media['metadata']['width'], media['metadata']['height']):
                raise ValueError('video_worker_poster_invalid')
        files = {}
        for key, name, blob in (('video', 'movie.mp4', media['video']), ('poster', 'poster.jpg', media['poster']),
                                ('metadata', 'media.json', canonical(media['metadata']))):
            with (output / name).open('xb') as handle:
                handle.write(blob)
            files[key] = {'bytes': len(blob), 'sha256': digest(blob)}
        atomic_json(directory / 'result.json', {'job_id': job['job_id'], 'descriptor_sha256': digest(raw),
            'code_sha256': job['code_sha256'], 'entry_sha256': job['entry_sha256'], 'files': files})
        progress('ready')
        return 0
    except Exception as exc:
        detail = {'type': type(exc).__name__, 'message': str(exc)}
        try:
            progress('error')
        except Exception as progress_error:
            detail['progress_error'] = str(progress_error)
        atomic_json(directory / 'worker-error.json', detail)
        return 1
    finally:
        if recorder is not None:
            recorder.abort()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--job', type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(run(args.job))
