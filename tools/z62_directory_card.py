"""Owned directory storage for the explicitly substituted (level C) camera.

This is not an SD/FAT emulation and is never mounted by the firmware. Only a
new directory or a directory carrying this format's manifest can be opened.
The manifest is the commit point; published JPEGs are immutable until delete.
"""
from copy import deepcopy
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import re
import stat
import threading
import uuid

from PIL import Image

FORMAT = 'Z62-QEMU-directory-card-C-v1'
MANIFEST = '.z62-camera.json'
LOCK = '.z62-camera.lock'
NAME = re.compile(r'Z62_[0-9]{4}\.JPG\Z')


class CardError(ValueError):
    pass


def plain_path(path, *, directory=None):
    """Reject links/reparse points in the supplied path before resolving it."""
    path = Path(os.path.abspath(path))
    if path.drive.startswith('\\\\'):
        raise CardError('invalid_card: network and device paths are not supported')
    for component in (*reversed(path.parents), path):
        if not component.exists() and not component.is_symlink():
            continue
        info = component.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise CardError('invalid_card: links and reparse points are not supported')
    if directory is True and not path.is_dir():
        raise CardError('invalid_card: expected an ordinary directory')
    if directory is False and not path.is_file():
        raise CardError('invalid_card: expected an ordinary file')
    return path


def require(condition):
    if not condition:
        raise ValueError('Malformed directory-card catalog')


def encode(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                       separators=(',', ':')) + '\n').encode('utf-8')


class DirectoryCard:
    @classmethod
    def create(cls, path, *, capacity_bytes=256 * 1024 * 1024):
        if type(capacity_bytes) is not int or not 1 <= capacity_bytes <= 1 << 40:
            raise CardError('invalid_capacity: expected 1..1099511627776 payload bytes')
        path = plain_path(path)
        if path == Path(path.anchor) or path.exists():
            raise CardError('invalid_card: creation requires a new dedicated directory')
        plain_path(path.parent, directory=True)
        path.mkdir()
        (path / 'DCIM').mkdir()
        (path / 'DCIM' / '100Z62EM').mkdir()
        data = {'format': FORMAT, 'id': uuid.uuid4().hex, 'capacity_bytes': capacity_bytes,
                'next_number': 1, 'images': []}
        with (path / MANIFEST).open('xb') as handle:
            handle.write(encode(data))
            handle.flush()
            os.fsync(handle.fileno())
        return cls(path)

    def __init__(self, path):
        self.root = plain_path(path, directory=True)
        self.image_directory = plain_path(self.root / 'DCIM' / '100Z62EM', directory=True)
        self._manifest = self.root / MANIFEST
        self._lock_path = self.root / LOCK
        self._mutex = threading.RLock()
        self._closed = True
        raw = plain_path(self._manifest, directory=False).read_bytes()
        self._data = self._decode(raw)
        self._expected = hashlib.sha256(raw).hexdigest()
        self._token = encode({'id': self._data['id'], 'pid': os.getpid(), 'lease': uuid.uuid4().hex})
        try:
            with self._lock_path.open('xb') as handle:
                handle.write(self._token)
        except FileExistsError as exc:
            raise CardError('card_busy: an existing lease must not be bypassed') from exc
        self._closed = False
        try:
            expected = {row['name'] for row in self._data['images']}
            actual = {p.name for p in self.image_directory.iterdir()}
            if actual != expected:
                raise CardError('recovery_required: image directory differs from committed catalog')
            for name in expected:
                plain_path(self.image_directory / name, directory=False)
        except BaseException:
            self.close()
            raise

    @staticmethod
    def _decode(raw):
        if len(raw) > 16 * 1024 * 1024:
            raise CardError('invalid_card: catalog exceeds the supported size')
        try:
            data = json.loads(raw)
            require(data['format'] == FORMAT)
            require(isinstance(data['id'], str) and re.fullmatch('[0-9a-f]{32}', data['id']))
            require(type(data['capacity_bytes']) is int and 1 <= data['capacity_bytes'] <= 1 << 40)
            require(type(data['next_number']) is int and 1 <= data['next_number'] <= 10000)
            require(isinstance(data['images'], list) and len(data['images']) < data['next_number'])
            names = []
            for row in data['images']:
                require(isinstance(row['name'], str) and NAME.fullmatch(row['name']))
                require(1 <= int(row['name'][4:8]) < data['next_number'])
                require(type(row['bytes']) is int and row['bytes'] > 0)
                require(isinstance(row['sha256'], str) and re.fullmatch('[0-9a-f]{64}', row['sha256']))
                require(isinstance(row['metadata'], dict) and row['metadata']['implementation_level'] == 'C')
                names.append(row['name'])
            require(len(set(names)) == len(names))
            require(sum(row['bytes'] for row in data['images']) <= data['capacity_bytes'])
        except (AssertionError, KeyError, TypeError, ValueError) as exc:
            raise CardError('invalid_card: missing or malformed owned-card catalog') from exc
        return data

    def _check(self):
        if self._closed:
            raise CardError('card_closed')
        plain_path(self.image_directory, directory=True)
        raw = plain_path(self._manifest, directory=False).read_bytes()
        if hashlib.sha256(raw).hexdigest() != self._expected:
            raise CardError('card_changed: catalog was modified outside this session')
        if plain_path(self._lock_path, directory=False).read_bytes() != self._token:
            raise CardError('card_changed: lease no longer belongs to this session')

    def _commit(self, data):
        self._check()
        raw = encode(data)
        temporary = self.root / ('.z62-camera-' + uuid.uuid4().hex + '.tmp')
        try:
            with temporary.open('xb') as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self._manifest)
        finally:
            if temporary.exists():
                temporary.unlink()
        self._data = data
        self._expected = hashlib.sha256(raw).hexdigest()

    def list(self):
        with self._mutex:
            self._check()
            return deepcopy(self._data['images'])

    def summary(self):
        images = self.list()
        used = sum(row['bytes'] for row in images)
        return {'present': True, 'implementation_level': 'C', 'format': FORMAT,
                'capacity_bytes': self._data['capacity_bytes'], 'used_payload_bytes': used,
                'free_payload_bytes': self._data['capacity_bytes'] - used, 'images': images}

    def store_jpeg(self, jpeg, metadata):
        with self._mutex:
            self._check()
            with Image.open(BytesIO(jpeg)) as image:
                image.load()
                if image.format != 'JPEG' or image.size != (metadata['width'], metadata['height']):
                    raise CardError('invalid_jpeg: format or dimensions differ from metadata')
            if metadata.get('implementation_level') != 'C':
                raise CardError('invalid_metadata: substitution must be explicit')
            if (sum(row['bytes'] for row in self._data['images']) + len(jpeg) > self._data['capacity_bytes']
                    or self._data['next_number'] > 9999):
                raise CardError('card_full')
            name = f"Z62_{self._data['next_number']:04d}.JPG"
            path = plain_path(self.image_directory / name)
            # Validate the whole metadata object before writing any image bytes.
            metadata = json.loads(encode(metadata))
            row = {'name': name, 'bytes': len(jpeg), 'sha256': hashlib.sha256(jpeg).hexdigest(),
                   'metadata': metadata}
            data = deepcopy(self._data)
            data['next_number'] += 1
            data['images'].append(row)
            created = False
            try:
                with path.open('xb') as handle:
                    created = True
                    handle.write(jpeg)
                    handle.flush()
                    os.fsync(handle.fileno())
                self._commit(data)
            except BaseException:
                if created:
                    plain_path(path, directory=False).unlink()
                raise
            return deepcopy(row)

    def _row(self, name):
        if not isinstance(name, str) or not NAME.fullmatch(name):
            raise CardError('invalid_image_name')
        for row in self._data['images']:
            if row['name'] == name:
                return row
        raise CardError('image_not_found')

    def read(self, name):
        with self._mutex:
            self._check()
            row = self._row(name)
            raw = plain_path(self.image_directory / name, directory=False).read_bytes()
            if len(raw) != row['bytes'] or hashlib.sha256(raw).hexdigest() != row['sha256']:
                raise CardError('corrupt_image: size or hash differs from committed photo')
            return raw

    def delete(self, name):
        with self._mutex:
            self.read(name)
            path = self.image_directory / name
            tombstone = self.root / ('.deleting-' + uuid.uuid4().hex)
            data = deepcopy(self._data)
            data['images'] = [row for row in data['images'] if row['name'] != name]
            os.replace(path, tombstone)
            try:
                self._commit(data)
            except BaseException:
                os.replace(tombstone, path)
                raise
            tombstone.unlink()

    def close(self):
        with self._mutex:
            if self._closed:
                return
            if plain_path(self._lock_path, directory=False).read_bytes() != self._token:
                raise CardError('card_changed: refusing to remove another lease')
            self._lock_path.unlink()
            self._closed = True

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
