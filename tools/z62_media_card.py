"""Versioned grouped-photo catalog, reusing the r22 card's ownership primitives.

Each image file is represented in the committed file set; each shutter is one
photo item. JPEG+NEF publishes one catalog transaction and deletes as a group.
Legacy v1 cards are never upgraded implicitly.
"""
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
    from .z62_directory_card import DirectoryCard, CardError, plain_path, encode, require
    from .z62_nef_codec import inspect_nef
except ImportError:
    from z62_directory_card import DirectoryCard, CardError, plain_path, encode, require
    from z62_nef_codec import inspect_nef

FORMAT = 'Z62-QEMU-media-card-C-v2'
NAME = re.compile(r'Z62_[0-9]{4}\.(JPG|NEF)\Z')


class MediaCard(DirectoryCard):
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
            names = []
            for row in data['images']:
                require(isinstance(row['name'], str) and NAME.fullmatch(row['name']))
                require(1 <= int(row['name'][4:8]) < data['next_number'])
                require(type(row['bytes']) is int and row['bytes'] > 0)
                require(isinstance(row['sha256'], str) and re.fullmatch('[0-9a-f]{64}', row['sha256']))
                require(isinstance(row['metadata'], dict) and row['metadata']['implementation_level'] == 'C')
                names.append(row['name'])
            require(len(names) == len(set(names)))
            grouped = []
            for item in data['items']:
                require(item['kind'] == 'photo' and item['metadata']['implementation_level'] == 'C')
                require(isinstance(item['files'], list) and 1 <= len(item['files']) <= 2)
                members = [row['name'] for row in item['files']]
                require(item['name'] in members and all(name[:8] == item['name'][:8] for name in members))
                for row in item['files']:
                    actual = next(f for f in data['images'] if f['name'] == row['name'])
                    require(row['bytes'] == actual['bytes'] and row['sha256'] == actual['sha256'])
                grouped.extend(members)
            require(sorted(grouped) == sorted(names))
            require(len(data['items']) < data['next_number'])
            require(sum(row['bytes'] for row in data['images']) <= data['capacity_bytes'])
        except (KeyError, TypeError, ValueError, StopIteration) as exc:
            raise CardError('invalid_card: expected an owned v2 media catalog') from exc
        return data

    def _row(self, name):
        if not isinstance(name, str) or not NAME.fullmatch(name):
            raise CardError('invalid_image_name')
        for row in self._data['images']:
            if row['name'] == name:
                return row
        raise CardError('image_not_found')

    def item(self, name):
        with self._mutex:
            self._check()
            for item in self._data['items']:
                if name in [row['name'] for row in item['files']]:
                    return deepcopy(item)
            raise CardError('image_not_found')

    def list(self):
        with self._mutex:
            self._check()
            return deepcopy(self._data['items'])

    def summary(self):
        with self._mutex:
            self._check()
            used = sum(row['bytes'] for row in self._data['images'])
            return {'present': True, 'implementation_level': 'C', 'format': FORMAT,
                    'capacity_bytes': self._data['capacity_bytes'], 'used_payload_bytes': used,
                    'free_payload_bytes': self._data['capacity_bytes'] - used, 'images': self.list()}

    def store_jpeg(self, jpeg, metadata):
        return self.store_photo(jpeg=jpeg, nef=None, metadata=metadata)

    def store_photo(self, *, jpeg, nef, metadata):
        with self._mutex:
            self._check()
            if metadata.get('implementation_level') != 'C' or jpeg is None and nef is None:
                raise CardError('invalid_photo')
            if jpeg is not None:
                with Image.open(BytesIO(jpeg)) as image:
                    image.load()
                    if image.format != 'JPEG' or image.size != (metadata['width'], metadata['height']):
                        raise CardError('invalid_jpeg')
            if nef is not None:
                info = inspect_nef(nef)
                if info['bits'] != 14 or info['compression'] != 34713 or not info['packed_fallback_excluded']:
                    raise CardError('invalid_nef: actual F0 lossless14 payload required')
            payloads = [('JPG', jpeg), ('NEF', nef)]
            payloads = [(extension, data) for extension, data in payloads if data is not None]
            used = sum(row['bytes'] for row in self._data['images'])
            if self._data['next_number'] > 9999 or used + sum(len(blob) for _, blob in payloads) > self._data['capacity_bytes']:
                raise CardError('card_full')
            metadata = json.loads(encode(metadata))
            number = self._data['next_number']
            files = [{'name': f'Z62_{number:04d}.{extension}', 'bytes': len(blob),
                      'sha256': hashlib.sha256(blob).hexdigest(), 'metadata': metadata}
                     for extension, blob in payloads]
            members = [{key: row[key] for key in ('name', 'bytes', 'sha256')} for row in files]
            item = {**deepcopy(files[0]), 'kind': 'photo', 'files': members,
                    'total_bytes': sum(row['bytes'] for row in files)}
            data = deepcopy(self._data)
            data['next_number'] += 1
            data['images'].extend(files)
            data['items'].append(item)
            created = []
            try:
                for row, (_, blob) in zip(files, payloads):
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

    def delete(self, name):
        with self._mutex:
            item = self.item(name)
            for row in item['files']:
                self.read(row['name'])
            removed = {row['name'] for row in item['files']}
            data = deepcopy(self._data)
            data['items'] = [row for row in data['items'] if row['name'] != item['name']]
            data['images'] = [row for row in data['images'] if row['name'] not in removed]
            moved = []
            try:
                for row in item['files']:
                    source = self.image_directory / row['name']
                    tombstone = self.root / ('.deleting-' + uuid.uuid4().hex)
                    os.replace(source, tombstone)
                    moved.append((source, tombstone))
                self._commit(data)
            except BaseException:
                for source, tombstone in reversed(moved):
                    os.replace(tombstone, source)
                raise
            for _, tombstone in moved:
                tombstone.unlink()
