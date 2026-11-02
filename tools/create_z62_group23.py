# SPDX-License-Identifier: GPL-2.0-or-later
"""Create only the existing synthetic zero-body group23 fixture, never calibration."""
import argparse
import hashlib
from pathlib import Path

EXPECTED = 'c7dd14358b45b2813fdee85fc587bcdd5899f7a81e0d5830513d631235bcc700'


def create(output):
    output = Path(output).absolute()
    if output.suffix.lower() != '.bin' or not str(output).isascii() or ',' in str(output):
        raise ValueError('Choose an ASCII regular .bin fixture path without commas')
    if str(output).startswith(('\\\\.\\', '\\\\?\\')) or any(p.is_symlink() or (
            hasattr(p, 'is_junction') and p.is_junction()) for p in (output, *output.parents)):
        raise ValueError('Device namespaces and linked fixture paths are not allowed')
    data = bytes(0xE0000-4)+b'ENDM'
    if hashlib.sha256(data).hexdigest() != EXPECTED:
        raise ValueError('Synthetic fixture identity mismatch')
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('xb') as handle:
        handle.write(data)
    print('Synthetic group23; factory_calibration=false; sha256='+EXPECTED)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    create(parser.parse_args().output)
