# SPDX-License-Identifier: GPL-2.0-or-later
"""Create blank virtual FAT32 media and safely stage persistent emulator cards.

Only regular .raw/.img files are supported, never physical drives. Persistence
is explicit: QEMU writes an ASCII staged copy, saved atomically after it exits.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import struct
import tempfile

VERSION = '2026.10.28-r4'


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def image_path(path, exists=True):
    path = Path(path).absolute()
    if path.is_symlink() or path.suffix.lower() not in ('.raw', '.img'):
        raise ValueError('Only non-symlink .raw/.img files are accepted')
    if exists:
        if not stat.S_ISREG(path.stat().st_mode):
            raise ValueError('Virtual card must be a regular file, not a device')
        if path.stat().st_size == 0 or path.stat().st_size % 512:
            raise ValueError('Virtual card size must be positive and sector aligned')
    return path.resolve()


def create_fat32(path, size_mib=512):
    """Exclusive creation of a blank MBR/FAT32 card, no camera files or firmware."""
    path = image_path(path, exists=False)
    if type(size_mib) is not int or size_mib not in (512, 1024, 2048, 4096, 8192, 16384, 32768):
        raise ValueError('Size must be a power of two from 512 to 32768 MiB')
    total = size_mib * 2048
    start, reserved, spc = 2048, 32, 8 if size_mib <= 4096 else 32
    sectors = total - start
    fat_sectors = 1
    while True:
        clusters = (sectors - reserved - 2 * fat_sectors) // spc
        needed = ((clusters + 2) * 4 + 511) // 512
        if fat_sectors >= needed:
            break
        fat_sectors = needed
    if not 65525 <= clusters < 0x0ffffff5:
        raise ValueError('Geometry outside FAT32 cluster bounds')
    mbr = bytearray(512)
    struct.pack_into('<B3sB3sII', mbr, 446, 0, b'\xfe\xff\xff', 0x0c,
                     b'\xfe\xff\xff', start, sectors)
    mbr[510:] = b'\x55\xaa'
    boot = bytearray(512)
    boot[:11] = b'\xeb\x58\x90Z62QEMU '
    struct.pack_into('<HBHBHHBHHHII', boot, 11, 512, spc, reserved, 2, 0, 0,
                     0xf8, 0, 63, 255, start, sectors)
    struct.pack_into('<IHHIHH', boot, 36, fat_sectors, 0, 0, 2, 1, 6)
    boot[64], boot[66] = 0x80, 0x29
    struct.pack_into('<I', boot, 67, 0x62317004)
    boot[71:82], boot[82:90] = b'Z62 VIRTUAL', b'FAT32   '
    boot[510:] = b'\x55\xaa'
    info = bytearray(512)
    struct.pack_into('<I', info, 0, 0x41615252)
    struct.pack_into('<IIII', info, 484, 0x61417272, clusters - 1, 3, 0)
    struct.pack_into('<I', info, 508, 0xaa550000)
    first_fat = struct.pack('<III', 0x0ffffff8, 0xffffffff, 0x0fffffff)
    with path.open('xb') as out:
        out.truncate(total * 512)
        def write_sector(number, data):
            out.seek(number * 512)
            out.write(data)
        write_sector(0, mbr)
        for offset in (0, 6):
            write_sector(start + offset, boot)
            write_sector(start + offset + 1, info)
        for index in range(2):
            write_sector(start + reserved + index * fat_sectors, first_fat)
        label = bytearray(32)
        label[:11], label[11] = b'Z62 VIRTUAL', 8
        write_sector(start + reserved + 2 * fat_sectors, label)
        out.flush()
        os.fsync(out.fileno())
    return {'version': VERSION, 'path': str(path), 'size_bytes': total * 512,
            'partition_start': start, 'fat_sectors': fat_sectors,
            'sectors_per_cluster': spc, 'clusters': clusters,
            'filesystem': 'FAT32', 'camera_formatted': False}


class CardSession:
    """Cooperative exclusive writer; failed/conflicting saves retain staged media."""
    def __init__(self, source, work, mode='snapshot'):
        if mode not in ('snapshot', 'persistent'):
            raise ValueError('Unknown SD mode')
        self.source = image_path(source)
        self.mode = mode
        self.staged = Path(work).resolve() / 'virtual-sd.raw'
        if not str(self.staged).isascii() or ',' in str(self.staged):
            raise ValueError('Staged card needs an ASCII path without commas')
        self.lock = self.source.with_name(self.source.name + '.z62-lock')
        self.lock_owned = False
        self.committed = False
        try:
            if mode == 'persistent':
                with self.lock.open('x', encoding='utf-8') as stream:
                    self.lock_owned = True
                    json.dump({'pid': os.getpid(), 'staged': str(self.staged)}, stream)
            self.original_size = self.source.stat().st_size
            self.original_sha256 = digest(self.source)
            with self.staged.open('xb') as out, self.source.open('rb') as src:
                shutil.copyfileobj(src, out, 1024 * 1024)
            if digest(self.staged) != self.original_sha256:
                raise ValueError('Source card changed during staging')
        except BaseException:
            self.close()
            raise

    def record(self):
        return {'source': str(self.source), 'staged': str(self.staged), 'mode': self.mode,
                'source_sha256': self.original_sha256, 'size': self.original_size,
                'snapshot': self.mode == 'snapshot', 'saved': self.committed}

    def commit(self):
        if self.mode != 'persistent':
            return False
        if self.committed:
            raise ValueError('Card session already saved')
        if self.staged.stat().st_size != self.original_size:
            raise ValueError('Staged card changed size; recovery copy retained')
        if self.source.is_symlink() or digest(self.source) != self.original_sha256:
            raise ValueError('Source card changed externally; recovery copy retained')
        handle, pending = tempfile.mkstemp(prefix=self.source.name + '.saving-', dir=self.source.parent)
        pending = Path(pending)
        try:
            with os.fdopen(handle, 'wb') as out, self.staged.open('rb') as src:
                shutil.copyfileobj(src, out, 1024 * 1024)
                out.flush()
                os.fsync(out.fileno())
            if digest(pending) != digest(self.staged):
                raise ValueError('Card copy verification failed')
            # Check again after the potentially long copy; never silently overwrite
            # changes from another editor that does not honor our sidecar lock.
            if self.source.is_symlink() or digest(self.source) != self.original_sha256:
                raise ValueError('Source card changed during save; recovery copy retained')
            os.replace(pending, self.source)
            self.committed = True
            return True
        finally:
            pending.unlink(missing_ok=True)

    def close(self):
        if self.lock_owned:
            self.lock.unlink(missing_ok=True)
            self.lock_owned = False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', action='version', version=VERSION)
    parser.add_argument('--create', type=Path, required=True)
    parser.add_argument('--size-mib', type=int, default=512)
    args = parser.parse_args()
    print(json.dumps(create_fat32(args.create, args.size_mib), indent=2))


if __name__ == '__main__':
    main()
