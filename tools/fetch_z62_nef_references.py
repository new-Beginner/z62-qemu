"""Fetch read-only public NEF format references, retaining versions and SHA256.

No downloaded code is executed. This does not fetch a Nikon SDK, private
codec, camera data or firmware. Output must be a fresh directory.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.request import Request, urlopen


def fetch(url, limit=4 * 1024 * 1024):
    request = Request(url, headers={'User-Agent': 'Z62-QEMU-offline-format-research'})
    with urlopen(request, timeout=45) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError('Reference exceeds bounded size: ' + url)
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    rows = []

    def save(name, url):
        data = fetch(url)
        with (args.output / name).open('xb') as handle:
            handle.write(data)
        rows.append({'file': name, 'url': url, 'bytes': len(data),
                     'sha256': hashlib.sha256(data).hexdigest()})
        return data

    commit = json.loads(save('libraw-commit.json', 'https://api.github.com/repos/LibRaw/LibRaw/commits/0.21.4'))['sha']
    for name in ('src/decoders/decoders_dcraw.cpp', 'src/metadata/nikon.cpp',
                 'src/metadata/identify.cpp', 'src/metadata/tiff.cpp', 'src/postprocessing/mem_image.cpp',
                 'COPYRIGHT', 'LICENSE.LGPL'):
        save('libraw-' + name.replace('/', '-'), f'https://raw.githubusercontent.com/LibRaw/LibRaw/{commit}/{name}')
    save('nikon-nef-recording.html', 'https://onlinemanual.nikonimglib.com/z7II_z6II/en/09_menu_guide_03_09.html')
    save('nef-format-notes.md', 'https://raw.githubusercontent.com/lclevy/nikon_nef/main/readme.md')
    root = Path(__file__).resolve().parents[1]
    source = root / 'third_party/z9-qemu/qemu/nikon-expeed-lossless.h'
    data = source.read_bytes()
    with (args.output / 'reference-lossless14.h').open('xb') as handle:
        handle.write(data)
    rows.append({'file': 'reference-lossless14.h', 'local_source': str(source),
                 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
                 'license': 'GPL-2.0-or-later, Copyright 2026 RdWing'})
    result = {'schema': 1, 'retrieved_utc': datetime.now(timezone.utc).isoformat(),
              'libraw_tag': '0.21.4', 'libraw_commit': commit, 'files': rows,
              'purpose': 'Format/decoder study only; no code execution or Nikon firmware equivalence claim'}
    with (args.output / 'manifest.json').open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
