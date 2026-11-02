"""Bounded read-only FAT32 inventory of an emulator-owned regular card image.

Lists short names, sizes, cluster chains and signatures. A matching signature
alone never establishes a valid encoded photograph or a successful shutter run.
"""
import argparse
import json
from pathlib import Path
import struct
from z62_virtual_sd import image_path


class Fat32:
    def __init__(self, path):
        self.path = image_path(path)
        self.size = self.path.stat().st_size
        self.stream = self.path.open('rb')
        try:
            mbr = self.read(0, 512)
            if mbr[510:512] != b'\x55\xaa':
                raise ValueError('Missing MBR signature')
            entries = [struct.unpack_from('<B3sB3sII', mbr, 446+16*i) for i in range(4)]
            fat = [e for e in entries if e[2] in (0x0b, 0x0c)]
            if len(fat) != 1:
                raise ValueError('Exactly one FAT32 MBR partition required')
            self.start, partition_sectors = fat[0][4:6]
            if not self.start or (self.start+partition_sectors)*512 > self.size:
                raise ValueError('Partition exceeds image')
            boot = self.read(self.start*512, 512)
            if boot[510:512] != b'\x55\xaa':
                raise ValueError('Missing FAT32 boot signature')
            self.bps = struct.unpack_from('<H', boot, 11)[0]
            self.spc = boot[13]
            reserved = struct.unpack_from('<H', boot, 14)[0]
            self.fats = boot[16]
            self.total, self.fat_sectors = struct.unpack_from('<II', boot, 32)
            flags = struct.unpack_from('<H', boot, 40)[0]
            self.root = struct.unpack_from('<I', boot, 44)[0]
            if (self.bps != 512 or self.spc not in (1,2,4,8,16,32,64,128) or
                    not reserved or not 1 <= self.fats <= 2 or not self.fat_sectors or
                    not self.total or self.total > partition_sectors):
                raise ValueError('Unsupported or invalid FAT32 geometry')
            active = flags & 15 if flags & 0x80 else 0
            if active >= self.fats:
                raise ValueError('Invalid active FAT index')
            self.data_sector = self.start + reserved + self.fats*self.fat_sectors
            available = self.total - reserved - self.fats*self.fat_sectors
            self.clusters = available // self.spc
            if not 65525 <= self.clusters < 0x0ffffff5 or (self.clusters+2)*4 > self.fat_sectors*512:
                raise ValueError('Invalid FAT32 cluster or table capacity')
            self.fat_offset = (self.start + reserved + active*self.fat_sectors)*512
            self.cluster_bytes = self.spc*512
            self.valid_cluster(self.root)
        except BaseException:
            self.stream.close()
            raise

    def read(self, offset, length):
        if offset < 0 or length < 0 or offset+length > self.size:
            raise ValueError('Read outside regular image')
        self.stream.seek(offset)
        result = self.stream.read(length)
        if len(result) != length:
            raise ValueError('Short card read')
        return result

    def valid_cluster(self, cluster):
        if not 2 <= cluster < self.clusters+2:
            raise ValueError('Invalid data cluster')

    def chain(self, first, limit=65536):
        seen = set()
        current = first
        while True:
            self.valid_cluster(current)
            if current in seen:
                raise ValueError('FAT cluster-chain cycle')
            if len(seen) >= limit:
                raise ValueError('Cluster-chain observation limit')
            seen.add(current)
            yield current
            following = struct.unpack('<I', self.read(self.fat_offset+current*4, 4))[0] & 0x0fffffff
            if following >= 0x0ffffff8:
                break
            if following < 2 or following >= 0x0ffffff0:
                raise ValueError('Unallocated/reserved/bad cluster in chain')
            current = following

    def cluster(self, number):
        self.valid_cluster(number)
        return self.read((self.data_sector+(number-2)*self.spc)*512, self.cluster_bytes)

    def inventory(self, entry_limit=2048, depth_limit=8):
        result = []
        visited = set()
        def walk(first, prefix, depth):
            if depth > depth_limit or first in visited:
                raise ValueError('Directory cycle/depth limit')
            visited.add(first)
            for cluster in self.chain(first, 512):
                data = self.cluster(cluster)
                for offset in range(0, len(data), 32):
                    entry = data[offset:offset+32]
                    if entry[0] == 0:
                        return
                    if entry[0] == 0xe5 or entry[11] == 0x0f or entry[11] & 8:
                        continue
                    name = entry[:8].decode('ascii', errors='replace').rstrip()
                    ext = entry[8:11].decode('ascii', errors='replace').rstrip()
                    if name in ('.', '..'):
                        continue
                    path = prefix + name + ('.'+ext if ext else '')
                    first_cluster = struct.unpack_from('<H', entry, 26)[0] | struct.unpack_from('<H', entry, 20)[0] << 16
                    size = struct.unpack_from('<I', entry, 28)[0]
                    directory = bool(entry[11] & 0x10)
                    item = {'short_path': path, 'directory': directory,
                            'first_cluster': first_cluster, 'size': size}
                    result.append(item)
                    if len(result) > entry_limit:
                        raise ValueError('Directory-entry observation limit')
                    if directory:
                        walk(first_cluster, path+'/', depth+1)
                    elif size:
                        clusters = list(self.chain(first_cluster))
                        if len(clusters)*self.cluster_bytes < size:
                            raise ValueError('File size exceeds allocated chain')
                        header = self.cluster(first_cluster)[:min(64,size)]
                        item.update(chain_clusters=len(clusters), header_hex=header.hex(),
                                    format_hint='JPEG' if header[:3] == b'\xff\xd8\xff' else
                                    'TIFF/NEF' if header[:4] in (b'II*\0', b'MM\0*') else 'unknown')
        walk(self.root, '/', 0)
        return result

    def close(self):
        self.stream.close()


def inspect(path):
    reader = Fat32(path)
    try:
        return {'path': str(reader.path), 'size_bytes': reader.size,
                'partition_start': reader.start, 'root_cluster': reader.root,
                'sectors_per_cluster': reader.spc, 'read_only': True,
                'long_names_decoded': False, 'files': reader.inventory(),
                'photo_saved_verified': False}
    finally:
        reader.close()


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('card', type=Path)
    p.add_argument('--output', type=Path)
    args = p.parse_args()
    result = inspect(args.card)
    if args.output:
        with args.output.open('x', encoding='utf-8') as out:
            json.dump(result, out, indent=2)
    print(json.dumps(result, indent=2))
