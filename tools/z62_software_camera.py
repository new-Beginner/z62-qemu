"""Deterministic scene/optics/JPEG camera, explicitly level C, not Nikon ISP/AF.

All times are supplied virtual nanoseconds. No wall-clock loop, camera API,
firmware RAM write, AF replacement or proprietary file-header emulation exists
in this backend. A QEMU adapter may supply its clock and forward user events.
"""
from copy import deepcopy
from dataclasses import dataclass
import hashlib
from io import BytesIO
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

VERSION = '2026.11.01-software-camera-r22'
FPS = 30
SECOND = 1_000_000_000


class CameraError(ValueError):
    pass


def number(value, low, high, label):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise CameraError('invalid_' + label)
    return value


def fields(payload, allowed):
    if not isinstance(payload, dict) or not set(payload) <= set(allowed):
        raise CameraError('invalid_event_fields')


@dataclass
class Frame:
    image: Image.Image
    metadata: dict


class Scene:
    def __init__(self, image=None, *, depth=.65, seed=62):
        self.depth = number(depth, 0, 1, 'scene_depth')
        if type(seed) is not int or not 0 <= seed <= 0xffffffff:
            raise CameraError('invalid_scene_seed')
        self.seed = seed
        self.image = image.convert('RGB').copy() if image is not None else None
        identity = (b'procedural-chart-v1:' + str(seed).encode() if self.image is None else
                    str(self.image.size).encode() + self.image.tobytes())
        self.identity = {'kind': 'chart' if image is None else 'image', 'depth': depth,
                         'seed': seed, 'sha256': hashlib.sha256(identity).hexdigest()}

    @classmethod
    def from_image(cls, path, *, depth=.65):
        try:
            from .z62_directory_card import plain_path
        except ImportError:
            from z62_directory_card import plain_path
        with Image.open(plain_path(path, directory=False)) as image:
            if image.width * image.height > 24_000_000:
                raise CameraError('scene_too_large')
            image.load()
            return cls(image, depth=depth)

    def render(self, width, height, frame_id):
        if self.image is not None:
            return self.image.resize((width, height), Image.Resampling.LANCZOS)
        yy, xx = np.indices((height, width))
        cell = max(2, width // 40)
        checker = ((xx // cell + yy // cell + self.seed) & 1).astype(np.float64)
        gray = (45 + checker * 150).astype(np.uint8)
        pixels = np.repeat(gray[:, :, None], 3, axis=2)
        # Moving patch sits outside the focus-test centre. It proves that
        # consecutive frame IDs can carry different scene observations.
        side = max(4, width // 16)
        x = frame_id * 3 % (width - side + 1)
        y = min(height - side, int(height * .7))
        pixels[y:y + side, x:x + side] = [225, 40 + self.seed % 80, 25]
        return Image.fromarray(pixels)


class SoftwareCamera:
    def __init__(self, *, card=None, width=640, height=424, scene=None, clock_epoch='standalone'):
        if (type(width) is not int or type(height) is not int or not 64 <= width <= 4096
                or not 64 <= height <= 4096 or width * height > 8_000_000):
            raise CameraError('invalid_dimensions')
        self.card, self.width, self.height = card, width, height
        if not isinstance(clock_epoch, str) or not 1 <= len(clock_epoch) <= 128:
            raise CameraError('invalid_clock_epoch')
        self.clock_epoch = clock_epoch
        self.scene = scene or Scene()
        self.time_ns = 0
        self.powered = False
        self.mode = 'photo'
        self.half_held = self.full_held = False
        self.playback = None
        self.zoom = 1
        self.exposure = {'shutter_seconds': 1 / 125, 'iso': 100, 'compensation_ev': 0}
        self.lens = {'focal_length_mm': 50, 'aperture': 4, 'focus_position': 0.,
                     'focus_target': 0., 'travel': [0., 1.], 'speed_per_second': 1.,
                     'latency_ns': 50_000_000, 'command_id': 0, 'moving': False}
        self._focus_start = 0.
        self._focus_start_ns = 0

    def _advance(self, now_ns):
        if type(now_ns) is not int or not self.time_ns <= now_ns <= (1 << 63) - 1:
            raise CameraError('invalid_virtual_time: expected monotonic integer nanoseconds')
        self.time_ns = now_ns
        if self.lens['moving']:
            elapsed = max(0, now_ns - self._focus_start_ns - self.lens['latency_ns']) / SECOND
            distance = self.lens['focus_target'] - self._focus_start
            moved = min(abs(distance), elapsed * self.lens['speed_per_second'])
            self.lens['focus_position'] = self._focus_start + math.copysign(moved, distance)
            self.lens['moving'] = moved < abs(distance)

    def _on(self):
        if not self.powered:
            raise CameraError('powered_off')

    def status(self, now_ns):
        self._advance(now_ns)
        return {'version': VERSION, 'implementation_level': 'C', 'virtual_time_ns': now_ns,
                'clock_epoch': self.clock_epoch,
                'frame_id': now_ns * FPS // SECOND, 'fps': FPS, 'powered': self.powered,
                'mode': self.mode, 'view': 'playback' if self.playback else 'live',
                'selected_image': self.playback, 'zoom': self.zoom,
                'half_pressed': self.half_held or self.full_held, 'full_pressed': self.full_held,
                'lens': deepcopy(self.lens), 'exposure': deepcopy(self.exposure),
                'scene': dict(self.scene.identity),
                'card': self.card.summary() if self.card else {'present': False},
                'capabilities': {'jpeg': True, 'nef': False, 'video': False, 'audio': False,
                                 'factory_af': False, 'factory_capture_chain': False,
                                 'qemu_sensor_scene_bridge': False}}

    def frame(self, now_ns):
        self._advance(now_ns)
        self._on()
        frame_id = now_ns * FPS // SECOND
        image = self.scene.render(self.width, self.height, frame_id)
        # The source spans the widest supported (24 mm) field of view.
        zoom = self.lens['focal_length_mm'] / 24.
        if zoom > 1:
            width, height = self.width / zoom, self.height / zoom
            left, top = (self.width - width) / 2, (self.height - height) / 2
            image = image.crop((left, top, left + width, top + height)).resize(
                (self.width, self.height), Image.Resampling.LANCZOS)
        radius = abs(self.lens['focus_position'] - self.scene.depth) * 18 * 4 / self.lens['aperture']
        if radius > .01:
            image = image.filter(ImageFilter.GaussianBlur(radius))
        gain = (self.exposure['shutter_seconds'] * 125 * self.exposure['iso'] / 100
                * (4 / self.lens['aperture']) ** 2 * 2 ** self.exposure['compensation_ev'])
        linear = (np.asarray(image, dtype=np.float64) / 255) ** 2.2
        pixels = np.rint(np.clip(linear * gain, 0, 1) ** (1 / 2.2) * 255).astype(np.uint8)
        image = Image.fromarray(pixels)
        metadata = {'schema': 1, 'version': VERSION, 'implementation_level': 'C',
                    'clock_epoch': self.clock_epoch,
                    'frame_id': frame_id, 'virtual_time_ns': now_ns, 'width': self.width,
                    'height': self.height, 'scene': dict(self.scene.identity),
                    'lens': deepcopy(self.lens), 'exposure': deepcopy(self.exposure),
                    'pixel_sha256': hashlib.sha256(image.tobytes()).hexdigest(),
                    'optics': 'synthetic single-plane blur and exposure gain; uncalibrated',
                    'factory_isp': False, 'factory_af': False}
        return Frame(image, metadata)

    def display(self, now_ns):
        self._advance(now_ns)
        self._on()
        if not self.playback:
            return self.frame(now_ns)
        raw = self.card.read(self.playback)
        with Image.open(BytesIO(raw)) as image:
            image.load()
            image = image.convert('RGB')
        metadata = next(row['metadata'] for row in self.card.list() if row['name'] == self.playback)
        if self.zoom > 1:
            width, height = image.width / self.zoom, image.height / self.zoom
            left, top = (image.width - width) / 2, (image.height - height) / 2
            image = image.crop((left, top, left + width, top + height)).resize(
                (self.width, self.height), Image.Resampling.NEAREST)
        return Frame(image, dict(metadata, display_virtual_time_ns=now_ns, playback_zoom=self.zoom))

    def _capture(self, now_ns):
        if not self.card:
            raise CameraError('no_card')
        if self.mode != 'photo':
            raise CameraError('wrong_mode: still capture requires photo mode')
        frame = self.frame(now_ns)
        exif = Image.Exif()
        exif[270] = json.dumps(frame.metadata, sort_keys=True, separators=(',', ':'))
        exif[305] = 'Z62-QEMU explicit software backend C'
        output = BytesIO()
        frame.image.save(output, format='JPEG', quality=92, subsampling=0, exif=exif)
        return self.card.store_jpeg(output.getvalue(), frame.metadata)

    def event(self, kind, payload, now_ns):
        self._advance(now_ns)
        result = None
        if kind == 'power':
            fields(payload, ('on',))
            if type(payload.get('on')) is not bool:
                raise CameraError('invalid_power')
            self.powered = payload['on']
            if not self.powered:
                self.half_held = self.full_held = False
                self.playback, self.zoom = None, 1
                self.lens['focus_target'] = self.lens['focus_position']
                self.lens['moving'] = False
        else:
            self._on()
            if kind == 'exposure':
                fields(payload, ('shutter_seconds', 'iso', 'compensation_ev'))
                bounds = {'shutter_seconds': (1 / 8000, 30), 'iso': (100, 51200),
                          'compensation_ev': (-5, 5)}
                values = {key: number(value, *bounds[key], key) for key, value in payload.items()}
                self.exposure.update(values)
            elif kind == 'lens':
                fields(payload, ('focus_target', 'aperture', 'focal_length_mm'))
                bounds = {'focus_target': (0, 1), 'aperture': (1.8, 16), 'focal_length_mm': (24, 120)}
                values = {key: number(value, *bounds[key], key) for key, value in payload.items()}
                if 'focus_target' in values:
                    self._focus_start = self.lens['focus_position']
                    self._focus_start_ns = now_ns
                    self.lens['command_id'] += 1
                    self.lens['moving'] = values['focus_target'] != self._focus_start
                self.lens.update(values)
            elif kind == 'mode':
                fields(payload, ('mode',))
                if payload.get('mode') not in ('photo', 'video'):
                    raise CameraError('invalid_mode')
                self.mode = payload['mode']
                self.playback, self.zoom = None, 1
            elif kind == 'shutter':
                fields(payload, ('stage', 'pressed'))
                if payload.get('stage') not in ('half', 'full') or type(payload.get('pressed')) is not bool:
                    raise CameraError('invalid_shutter')
                pressed = payload['pressed']
                if payload['stage'] == 'half':
                    self.half_held = pressed
                else:
                    rising = pressed and not self.full_held
                    self.full_held = pressed
                    if rising:
                        result = self._capture(now_ns)
                if pressed:
                    self.playback, self.zoom = None, 1
            elif kind == 'playback':
                fields(payload, ('action',))
                action = payload.get('action')
                if action not in ('open', 'close', 'next', 'previous'):
                    raise CameraError('invalid_playback')
                if action == 'close':
                    self.playback = None
                else:
                    rows = self.card.list() if self.card else []
                    if not rows:
                        raise CameraError('no_images')
                    names = [row['name'] for row in rows]
                    index = names.index(self.playback) if self.playback else len(names) - 1
                    index += 1 if action == 'next' else -1 if action == 'previous' else 0
                    self.playback = names[index % len(names)]
                self.zoom = 1
            elif kind == 'zoom':
                fields(payload, ('factor',))
                if type(payload.get('factor')) is not int or payload['factor'] not in (1, 2, 4, 8, 16):
                    raise CameraError('invalid_zoom')
                if not self.playback:
                    raise CameraError('playback_required')
                self.zoom = payload['factor']
            elif kind == 'delete':
                fields(payload, ())
                if not self.playback:
                    raise CameraError('playback_required')
                result = {'deleted': self.playback}
                self.card.delete(self.playback)
                rows = self.card.list()
                self.playback = rows[-1]['name'] if rows else None
                self.zoom = 1
            else:
                raise CameraError('unsupported_event: ' + str(kind))
        return {'state': self.status(now_ns), 'result': result}
