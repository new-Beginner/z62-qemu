"""r27 card: validate outside its lock, publish atomically, expose compact views."""
from copy import deepcopy
import hashlib
from io import BytesIO
import json
import os

from PIL import Image

try:
    from .z62_video_card import VideoCard, validate_video_metadata
    from .z62_directory_card import CardError, plain_path, encode
except ImportError:
    from z62_video_card import VideoCard, validate_video_metadata
    from z62_directory_card import CardError, plain_path, encode


def compact_item(item):
    if item['kind'] != 'video':
        return deepcopy(item)
    result = {key: deepcopy(value) for key, value in item.items() if key != 'metadata'}
    metadata = item['metadata']
    keep = ('implementation_level', 'video_writer', 'factory_encoder', 'audio', 'codec', 'container',
            'width', 'height', 'clock_epoch', 'start_request_ns', 'stop_request_ns', 'first_source_ns',
            'duration_us', 'source_map_sha256')
    result['metadata'] = {key: deepcopy(metadata[key]) for key in keep if key in metadata}
    result['metadata']['frame_count'] = len(metadata['samples'])
    result['detail_url'] = '/software/item/' + item['name']
    return result


class AsyncVideoCard(VideoCard):
    def list(self):
        with self._mutex:
            self._check()
            return [compact_item(row) for row in self._data['items']]

    def item(self, name):
        with self._mutex:
            self._check()
            for row in self._data['items']:
                if name in [member['name'] for member in row['files']]:
                    return compact_item(row)
            raise CardError('image_not_found')

    def full_item(self, name):
        return super().item(name)

    def store_video(self, *, video, poster, metadata):
        # No lock is held while FFprobe/FFmpeg decode or check the timeline.
        validate_video_metadata(video, metadata)
        self._check_poster(poster, metadata)
        return self._publish_media(video, poster, metadata)

    def commit_verified(self, result):
        if isinstance(result, dict):
            raise CardError('unowned_movie_result')
        try:
            from .z62_async_video_job import OwnedVideoResult
        except ImportError:
            from z62_async_video_job import OwnedVideoResult
        if not isinstance(result, OwnedVideoResult) or not result.is_verified():
            raise CardError('unowned_movie_result')
        result.check_bytes()
        self._check_poster(result.poster, result.metadata)
        return self._publish_media(result.video, result.poster, result.metadata)

    @staticmethod
    def _check_poster(poster, metadata):
        with Image.open(BytesIO(poster)) as image:
            image.load()
            if image.format != 'JPEG' or image.size != (metadata['width'], metadata['height']):
                raise CardError('invalid_video_poster')

    def _publish_media(self, video, poster, metadata):
        metadata = json.loads(encode(metadata))
        with self._mutex:
            self._check()
            used = sum(row['bytes'] for row in self._data['images'])
            if self._data['next_number'] > 9999 or used + len(video) + len(poster) > self._data['capacity_bytes']:
                raise CardError('card_full')
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
            return compact_item(item)
