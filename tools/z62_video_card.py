"""Owned v3 photo/video catalog; finalized movies and their posters commit together."""
from copy import deepcopy
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import re
import uuid

from PIL import Image

try:
    from .z62_media_card import MediaCard
    from .z62_directory_card import CardError, plain_path, encode, require
    from .z62_video_codec import audit_video
except ImportError:
    from z62_media_card import MediaCard
    from z62_directory_card import CardError, plain_path, encode, require
    from z62_video_codec import audit_video

FORMAT = 'Z62-QEMU-video-card-C-v3'
NAME = re.compile(r'Z62_[0-9]{4}\.(JPG|NEF|MP4)\Z')


def validate_video_metadata(video, metadata):
    require(metadata['implementation_level'] == 'C' and metadata['factory_encoder'] is False and metadata['audio'] is False)
    samples = metadata['samples']
    require(isinstance(samples, list) and 2 <= len(samples) <= 1800)
    origin = samples[0]['virtual_time_ns']
    expected = [(row['virtual_time_ns'] - origin) // 1000 for row in samples]
    require(metadata['timestamps_us'] == expected and expected[0] == 0)
    require(all(b > a for a, b in zip(expected, expected[1:])))
    require(metadata['duration_us'] == (metadata['stop_request_ns'] - origin) // 1000 > expected[-1])
    require(metadata['source_map_sha256'] == hashlib.sha256(json.dumps(samples, sort_keys=True,
                                                 separators=(',', ':')).encode()).hexdigest())
    audit = audit_video(video)
    require(audit['width'] == metadata['width'] and audit['height'] == metadata['height'])
    require(audit['timestamps_us'] == expected and audit['duration_us'] == metadata['duration_us'])
    if metadata['codec'] == 'libx264rgb-lossless':
        require(audit['pixel_sha256'] == [row['pixel_sha256'] for row in samples])
    else:
        require(metadata['codec'] == 'libx264-yuv420p-crf18' and audit['pixel_format'] == 'yuv420p')
        require(audit['pixel_sha256'] == metadata['encoded_pixel_sha256'])
        require(len(metadata['independent_audit']['source_mse']) == len(samples))
        require(all(0 <= value <= 1000 for value in metadata['independent_audit']['source_mse']))
    return audit


class VideoCard(MediaCard):
    @classmethod
    def create(cls, path, *, capacity_bytes=256 * 1024 * 1024):
        if type(capacity_bytes) is not int or not 1 <= capacity_bytes <= 1 << 40:
            raise CardError('invalid_capacity')
        path = plain_path(path)
        if path == Path(path.anchor) or path.exists():
            raise CardError('invalid_card: creation requires a new dedicated directory')
        plain_path(path.parent, directory=True)
        path.mkdir()
        (path / 'DCIM').mkdir()
        (path / 'DCIM/100Z62EM').mkdir()
        data = {'format': FORMAT, 'id': uuid.uuid4().hex, 'capacity_bytes': capacity_bytes,
                'next_number': 1, 'images': [], 'items': []}
        with (path / '.z62-camera.json').open('xb') as handle:
            handle.write(encode(data))
            handle.flush()
            os.fsync(handle.fileno())
        return cls(path)

    @staticmethod
    def _decode(raw):
        try:
            require(len(raw) <= 64 * 1024 * 1024)
            data = json.loads(raw)
            require(data['format'] == FORMAT)
            require(isinstance(data['id'], str) and re.fullmatch('[0-9a-f]{32}', data['id']))
            require(type(data['capacity_bytes']) is int and 1 <= data['capacity_bytes'] <= 1 << 40)
            require(type(data['next_number']) is int and 1 <= data['next_number'] <= 10000)
            require(isinstance(data['images'], list) and isinstance(data['items'], list))
            files = {}
            for row in data['images']:
                name = row['name']
                require(isinstance(name, str) and NAME.fullmatch(name) and name not in files)
                require(1 <= int(name[4:8]) < data['next_number'])
                require(type(row['bytes']) is int and row['bytes'] > 0)
                require(isinstance(row['sha256'], str) and re.fullmatch('[0-9a-f]{64}', row['sha256']))
                require(isinstance(row['metadata'], dict) and row['metadata']['implementation_level'] == 'C')
                files[name] = row
            grouped = []
            for item in data['items']:
                require(item['kind'] in ('photo', 'video'))
                require(isinstance(item['files'], list) and 1 <= len(item['files']) <= 2)
                members = [row['name'] for row in item['files']]
                require(len(set(members)) == len(members) and item['name'] in members)
                require(all(name[:8] == item['name'][:8] for name in members))
                primary = files[item['name']]
                require(all(item[key] == primary[key] for key in ('bytes', 'sha256', 'metadata')))
                for row in item['files']:
                    require(row['bytes'] == files[row['name']]['bytes'] and row['sha256'] == files[row['name']]['sha256'])
                    require(files[row['name']]['metadata'] == item['metadata'])
                require(item['total_bytes'] == sum(row['bytes'] for row in item['files']))
                if item['kind'] == 'video':
                    require(item['name'].endswith('.MP4') and len(members) == 2 and item['poster'] in members)
                    require(item['poster'].endswith('.JPG') and item['metadata']['audio'] is False)
                else:
                    require(all(name.endswith(('.JPG', '.NEF')) for name in members))
                grouped.extend(members)
            require(sorted(grouped) == sorted(files))
            require(len(data['items']) < data['next_number'])
            require(sum(row['bytes'] for row in files.values()) <= data['capacity_bytes'])
        except (KeyError, TypeError, ValueError) as exc:
            raise CardError('invalid_card: expected an owned v3 photo/video catalog') from exc
        return data

    def _row(self, name):
        if not isinstance(name, str) or not NAME.fullmatch(name):
            raise CardError('invalid_image_name')
        for row in self._data['images']:
            if row['name'] == name:
                return row
        raise CardError('image_not_found')

    def summary(self):
        summary = super().summary()
        summary['format'] = FORMAT
        summary['photos'] = sum(row['kind'] == 'photo' for row in summary['images'])
        summary['videos'] = sum(row['kind'] == 'video' for row in summary['images'])
        return summary

    def store_video(self, *, video, poster, metadata):
        with self._mutex:
            self._check()
            validate_video_metadata(video, metadata)
            with Image.open(BytesIO(poster)) as image:
                image.load()
                if image.format != 'JPEG' or image.size != (metadata['width'], metadata['height']):
                    raise CardError('invalid_video_poster')
            used = sum(row['bytes'] for row in self._data['images'])
            if self._data['next_number'] > 9999 or used + len(video) + len(poster) > self._data['capacity_bytes']:
                raise CardError('card_full')
            metadata = json.loads(encode(metadata))
            prefix = f"Z62_{self._data['next_number']:04d}"
            files = [{'name': prefix + extension, 'bytes': len(blob),
                      'sha256': hashlib.sha256(blob).hexdigest(), 'metadata': metadata}
                     for extension, blob in (('.MP4', video), ('.JPG', poster))]
            item = {**deepcopy(files[0]), 'kind': 'video', 'poster': files[1]['name'],
                    'files': [{key: row[key] for key in ('name', 'bytes', 'sha256')} for row in files],
                    'total_bytes': len(video) + len(poster)}
            data = deepcopy(self._data)
            data['next_number'] += 1
            data['images'].extend(files)
            data['items'].append(item)
            created = []
            try:
                for row, blob in zip(files, (video, poster)):
                    path = plain_path(self.image_directory / row['name'])
                    with path.open('xb') as handle:
                        created.append(path)
                        handle.write(blob)
                        handle.flush()
                        os.fsync(handle.fileno())
                self._commit(data)
            except BaseException:
                for path in created:
                    plain_path(path, directory=False).unlink()
                raise
            return deepcopy(item)
