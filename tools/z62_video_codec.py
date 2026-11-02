# SPDX-License-Identifier: GPL-2.0-or-later
"""C video: acknowledged RGB frames, explicit guest PTS/durations, real MP4.

PyAV/libx264 is a host substitute, never the Nikon video encoder. Only
unique consumed publications are encoded. External FFmpeg verifies every
decoded RGB hash and source error; FFprobe checks the complete time line.
"""
from copy import deepcopy
from decimal import Decimal
from fractions import Fraction
import hashlib
from io import BytesIO
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

import numpy as np
from PIL import Image

try:
    from .z62_directory_card import plain_path
    from .z62_nef_codec import raw14_from_consumed_frame
except ImportError:
    from z62_directory_card import plain_path
    from z62_nef_codec import raw14_from_consumed_frame

VERSION = '2026.11.01-video-codec-r26b'
TIME_BASE = Fraction(1, 1_000_000)
MAX_SOURCE_MSE = 1000.0
MAX_DECODED_BYTES = 2 * 1024 * 1024 * 1024


def backend():
    try:
        import av
    except ImportError as exc:
        raise ValueError('video_backend_unavailable: install requirements-video.txt in the video environment') from exc
    av.codec.Codec('libx264', 'w')
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        raise ValueError('video_backend_unavailable: independent ffmpeg and ffprobe are required')
    return av


def run(command):
    result = subprocess.run(command, capture_output=True, timeout=120)
    if result.returncode:
        raise ValueError('video_decoder_failed: ' + result.stderr.decode('utf-8', 'replace')[-3000:])
    return result.stdout


def audit_video(data, references=None, source_hashes=None):
    if not isinstance(data, bytes) or not 8 <= len(data) <= 256 * 1024 * 1024 or data[4:8] != b'ftyp':
        raise ValueError('video_invalid_mp4')
    with tempfile.TemporaryDirectory(prefix='z62-video-audit-') as directory:
        path = Path(directory) / 'actual.mp4'
        with path.open('xb') as handle:
            handle.write(data)
        info = json.loads(run([shutil.which('ffprobe') or 'ffprobe', '-v', 'error', '-show_frames',
            '-show_entries', 'stream=codec_type,codec_name,width,height,duration,time_base,pix_fmt,profile:frame=best_effort_timestamp_time',
            '-of', 'json', str(path)]))
        streams = info.get('streams', [])
        if len(streams) != 1 or streams[0].get('codec_type') != 'video':
            raise ValueError('video_requires_exactly_one_silent_video_stream')
        stream = streams[0]
        timestamps = [int(Decimal(row['best_effort_timestamp_time']) * 1_000_000)
                      for row in info.get('frames', [])]
        frame_bytes = stream['width'] * stream['height'] * 3
        if not 2 <= len(timestamps) <= 1800 or frame_bytes * len(timestamps) > MAX_DECODED_BYTES:
            raise ValueError('video_decoded_size_limit')
        decoded_path = Path(directory) / 'decoded.rgb'
        run([shutil.which('ffmpeg') or 'ffmpeg', '-hide_banner', '-v', 'error', '-threads', '1',
            '-i', str(path), '-map', '0:v:0', '-an', '-c:v', 'rawvideo', '-pix_fmt', 'rgb24',
            '-fps_mode', 'passthrough', '-f', 'rawvideo', str(decoded_path)])
        if decoded_path.stat().st_size != len(timestamps) * frame_bytes:
            raise ValueError('video_frame_count_mismatch')
        if references is not None and (len(references) != len(timestamps) or
                                      source_hashes is not None and len(source_hashes) != len(timestamps)):
            raise ValueError('video_reference_count_mismatch')
        hashes, errors = [], []
        with decoded_path.open('rb') as handle:
            for index in range(len(timestamps)):
                pixels = handle.read(frame_bytes)
                hashes.append(hashlib.sha256(pixels).hexdigest())
                if references is not None:
                    with Image.open(references[index]) as image:
                        expected = image.convert('RGB').tobytes()
                    if len(expected) != frame_bytes or (source_hashes is not None and
                            hashlib.sha256(expected).hexdigest() != source_hashes[index]):
                        raise ValueError('video_reference_pixels_changed')
                    difference = (np.frombuffer(pixels, dtype=np.uint8).astype(np.float32) -
                                  np.frombuffer(expected, dtype=np.uint8).astype(np.float32))
                    errors.append(float(np.mean(difference * difference)))
        result = {'codec': stream['codec_name'], 'width': stream['width'], 'height': stream['height'],
                'pixel_format': stream['pix_fmt'], 'profile': stream['profile'],
                'time_base': stream['time_base'], 'timestamps_us': timestamps,
                'duration_us': int(Decimal(stream['duration']) * 1_000_000), 'pixel_sha256': hashes,
                'independent_decoder': shutil.which('ffmpeg'), 'independent_probe': shutil.which('ffprobe')}
        if references is not None:
            result['source_mse'] = errors
            result['max_source_mse'] = max(errors)
        return result


class VideoRecorder:
    def __init__(self, directory, *, start_ns, clock_epoch, max_frames=1800,
                 max_buffer_bytes=256 * 1024 * 1024, max_duration_ns=60_000_000_000):
        self.av = backend()
        if (type(start_ns) is not int or start_ns < 0 or not isinstance(clock_epoch, str) or not clock_epoch or
                type(max_frames) is not int or not 2 <= max_frames <= 1800 or
                type(max_buffer_bytes) is not int or not 1 <= max_buffer_bytes <= 256 * 1024 * 1024 or
                type(max_duration_ns) is not int or not 1 <= max_duration_ns <= 60_000_000_000):
            raise ValueError('video_invalid_limits')
        directory = plain_path(directory, directory=True)
        self.temp = tempfile.TemporaryDirectory(prefix='z62-video-', dir=directory)
        self.work = Path(self.temp.name)
        self.start_ns, self.clock_epoch = start_ns, clock_epoch
        self.max_frames, self.max_bytes, self.max_duration = max_frames, max_buffer_bytes, max_duration_ns
        self.samples = []
        self.buffer_bytes = 0
        self.closed = False

    def status(self):
        return {'frames': len(self.samples), 'buffer_bytes': self.buffer_bytes,
                'start_request_ns': self.start_ns, 'closed': self.closed,
                'last_source_ns': self.samples[-1]['virtual_time_ns'] if self.samples else None}

    def append(self, frame):
        if self.closed:
            raise ValueError('video_recorder_closed')
        meta = frame.metadata
        if (meta.get('clock_epoch') != self.clock_epoch or frame.image.size != (meta.get('width'), meta.get('height')) or
                type(meta.get('virtual_time_ns')) is not int):
            raise ValueError('video_source_epoch_or_geometry_mismatch')
        # This helper also checks C ownership, frame/time identity, RGB hash,
        # and reconstructs the same acknowledged native packed12 payload.
        raw14_from_consumed_frame(frame)
        if meta['virtual_time_ns'] < self.start_ns:
            return False
        tag = meta['native_scene_source']
        if self.samples:
            previous = self.samples[-1]
            old = previous['native_scene_source']
            if tag['epoch'] != old['epoch']:
                raise ValueError('video_native_epoch_changed')
            if tag['publish_id'] == old['publish_id']:
                if tag != old or meta['pixel_sha256'] != previous['pixel_sha256']:
                    raise ValueError('video_publication_identity_changed')
                return False
            if (tag['publish_id'] < old['publish_id'] or
                    meta['virtual_time_ns'] <= previous['virtual_time_ns'] or
                    frame.image.size != (previous['width'], previous['height'])):
                raise ValueError('video_nonmonotonic_source')
        if len(self.samples) >= self.max_frames or meta['virtual_time_ns'] - self.start_ns >= self.max_duration:
            raise ValueError('video_buffer_limit')
        if (len(self.samples) + 1) * frame.image.width * frame.image.height * 3 > MAX_DECODED_BYTES:
            raise ValueError('video_decoded_size_limit')
        image = BytesIO()
        frame.image.convert('RGB').save(image, format='PNG')
        data = image.getvalue()
        if self.buffer_bytes + len(data) > self.max_bytes:
            raise ValueError('video_buffer_limit')
        path = self.work / f'frame-{len(self.samples):04d}.png'
        with path.open('xb') as handle:
            handle.write(data)
        self.samples.append(deepcopy(meta))
        self.buffer_bytes += len(data)
        return True

    def finish(self, stop_ns):
        if self.closed:
            raise ValueError('video_recorder_closed')
        if (type(stop_ns) is not int or len(self.samples) < 2 or
                stop_ns < self.samples[-1]['virtual_time_ns'] or stop_ns - self.start_ns > self.max_duration):
            raise ValueError('video_invalid_stop_or_insufficient_frames')
        samples = self.samples[:-1] if stop_ns == self.samples[-1]['virtual_time_ns'] else self.samples
        if len(samples) < 2:
            raise ValueError('video_invalid_stop_or_insufficient_frames')
        # The recording interval ends before a source sampled exactly at STOP.
        # Such a sample has no positive display duration; do not invent one.
        self.samples = samples
        first = self.samples[0]['virtual_time_ns']
        pts = [(row['virtual_time_ns'] - first) // 1000 for row in self.samples]
        end = (stop_ns - first) // 1000
        durations = [b - a for a, b in zip(pts, pts[1:] + [end])]
        if any(value <= 0 for value in durations):
            raise ValueError('video_timestamp_resolution')
        timeline_hash = hashlib.sha256(json.dumps(self.samples, sort_keys=True,
                                                  separators=(',', ':')).encode()).hexdigest()
        path = self.work / 'recording.mp4'
        try:
            with self.av.open(str(path), mode='w', format='mp4', options={
                    'movflags': '+faststart', 'video_track_timescale': '1000000',
                    'movie_timescale': '1000000', 'use_editlist': '0'}) as container:
                container.metadata['comment'] = VERSION + ' C synthetic acknowledged RGB; source-map-sha256=' + timeline_hash
                stream = container.add_stream('libx264', rate=30)
                stream.width, stream.height = self.samples[0]['width'], self.samples[0]['height']
                stream.pix_fmt = 'yuv420p'
                stream.time_base = stream.codec_context.time_base = TIME_BASE
                stream.codec_context.thread_count = 1
                stream.options = {'crf': '18', 'preset': 'ultrafast', 'tune': 'zerolatency', 'bf': '0'}
                duration_by_pts = dict(zip(pts, durations))

                def mux(packets):
                    for packet in packets:
                        if packet.time_base != TIME_BASE or packet.pts not in duration_by_pts:
                            raise ValueError('video_encoder_changed_timestamp_contract')
                        packet.duration = duration_by_pts[packet.pts]
                        container.mux(packet)

                for index, time_us in enumerate(pts):
                    with Image.open(self.work / f'frame-{index:04d}.png') as image:
                        frame = self.av.VideoFrame.from_image(image.convert('RGB'))
                    frame.pts, frame.time_base = time_us, TIME_BASE
                    mux(stream.encode(frame))
                mux(stream.encode(None))
            data = path.read_bytes()
            audit = audit_video(data, [self.work / f'frame-{index:04d}.png' for index in range(len(self.samples))],
                                [row['pixel_sha256'] for row in self.samples])
            if (audit['timestamps_us'] != pts or audit['duration_us'] != end or
                    audit['pixel_format'] != 'yuv420p' or audit['max_source_mse'] > MAX_SOURCE_MSE):
                raise ValueError('video_independent_pixel_or_timing_mismatch')
            poster = BytesIO()
            with Image.open(self.work / 'frame-0000.png') as image:
                image.save(poster, format='JPEG', quality=92, subsampling=0)
            metadata = {'implementation_level': 'C', 'video_writer': VERSION, 'factory_encoder': False,
                        'audio': False, 'codec': 'libx264-yuv420p-crf18', 'container': 'MP4',
                        'width': self.samples[0]['width'], 'height': self.samples[0]['height'],
                        'clock_epoch': self.clock_epoch, 'start_request_ns': self.start_ns,
                        'stop_request_ns': stop_ns, 'first_source_ns': first, 'duration_us': end,
                        'timestamps_us': pts, 'samples': deepcopy(self.samples), 'source_map_sha256': timeline_hash,
                        'encoded_pixel_sha256': audit['pixel_sha256'], 'source_mse_limit': MAX_SOURCE_MSE,
                        'pyav_version': self.av.__version__, 'libraries': self.av.library_versions,
                        'independent_audit': audit}
            return {'video': data, 'poster': poster.getvalue(), 'metadata': metadata}
        finally:
            self.abort()

    def abort(self):
        if not self.closed:
            self.temp.cleanup()
            self.closed = True
