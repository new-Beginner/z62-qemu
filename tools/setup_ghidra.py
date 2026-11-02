"""Fetch a pinned official portable Ghidra distribution for local Z62 analysis.

Uses the existing Java 21 installation. No system installation or firmware IO.
The archive digest is published on the official 11.4.2 release asset page.
"""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import tempfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DIST = 'ghidra_11.4.2_PUBLIC'
ARCHIVE_NAME = 'ghidra_11.4.2_PUBLIC_20250826.zip'
URL = 'https://github.com/NationalSecurityAgency/ghidra/releases/download/Ghidra_11.4.2_build/' + ARCHIVE_NAME
SHA256 = '795a02076af16257bd6f3f4736c4fc152ce9ff1f95df35cd47e2adc086e037a6'
TOOLS = ROOT / '.build/tools'


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for data in iter(lambda: stream.read(4*1024*1024), b''):
            value.update(data)
    return value.hexdigest()


def setup(runtime_root=None):
    TOOLS.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(TOOLS).free < 3*1024**3:
        raise ValueError('At least 3 GiB of free space required for the portable tool')
    archive = TOOLS/ARCHIVE_NAME
    destination = runtime_root or TOOLS/'ghidra-11.4.2'
    if runtime_root is not None:
        destination = runtime_root.resolve()
        if not str(destination).isascii():
            raise ValueError('Portable runtime path must be ASCII')
        destination.parent.mkdir(parents=True, exist_ok=True)
        if shutil.disk_usage(destination.parent).free < 3*1024**3:
            raise ValueError('At least 3 GiB of free space required on runtime volume')
    if not archive.exists():
        with tempfile.NamedTemporaryFile(prefix='ghidra-', suffix='.zip.part', dir=TOOLS, delete=False) as stream:
            partial = Path(stream.name)
            with urllib.request.urlopen(URL, timeout=60) as response:
                total, announced = 0, 0
                while data := response.read(4*1024*1024):
                    total += len(data)
                    if total > 600*1024**2:
                        raise ValueError('Unexpected oversized release archive')
                    stream.write(data)
                    if total-announced >= 64*1024**2:
                        print('Downloaded MiB:', total//1024**2, flush=True)
                        announced = total
        if digest(partial) != SHA256:
            raise ValueError('Official Ghidra archive hash mismatch; retained partial: ' + str(partial))
        # Same-directory exclusive publication; never replace another archive.
        os.link(partial, archive)
        partial.unlink()
    if archive.is_symlink() or digest(archive) != SHA256:
        raise ValueError('Cached Ghidra archive identity mismatch')
    manifest_path = destination/'installation.json'
    if destination.exists():
        record = json.loads(manifest_path.read_text(encoding='utf-8'))
        if record.get('archive_sha256') != SHA256 or not Path(record['headless']).is_file():
            raise ValueError('Existing portable installation is incomplete or different')
        return record
    with zipfile.ZipFile(archive) as package:
        entries = package.infolist()
        if len(entries) > 100000 or sum(e.file_size for e in entries) > 4*1024**3:
            raise ValueError('Unexpected archive expansion')
        for entry in entries:
            name = PurePosixPath(entry.filename)
            if (name.is_absolute() or '..' in name.parts or not name.parts or
                    name.parts[0] != DIST or '\\' in entry.filename or ':' in entry.filename or
                    stat.S_ISLNK(entry.external_attr >> 16)):
                raise ValueError('Unsafe release archive member: ' + entry.filename)
        destination.mkdir(exist_ok=False)
        package.extractall(destination)
    headless = destination/DIST/'support/analyzeHeadless.bat'
    if not headless.is_file():
        raise ValueError('Expected official headless launcher missing')
    record = {'version': '11.4.2', 'archive_url': URL, 'archive_sha256': SHA256,
              'headless': str(headless), 'java_requirement': 'JDK 21 64-bit',
              'release_page': 'https://github.com/NationalSecurityAgency/ghidra/releases/tag/Ghidra_11.4.2_build'}
    with manifest_path.open('x', encoding='utf-8') as stream:
        json.dump(record, stream, indent=2)
    return record


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ascii-runtime', action='store_true')
    args = parser.parse_args()
    runtime = Path(tempfile.gettempdir())/'z62-ghidra-runtime-11.4.2' if args.ascii_runtime else None
    result = setup(runtime)
    if runtime is not None:
        pointer = TOOLS/'ghidra-ascii.json'
        content = json.dumps(result, indent=2)
        if pointer.exists():
            if pointer.read_text(encoding='utf-8') != content:
                raise ValueError('Refusing different existing runtime locator')
        else:
            with pointer.open('x', encoding='utf-8') as stream:
                stream.write(content)
    print(json.dumps(result, indent=2))
