"""Independent RawPy/LibRaw pixel oracle for explicitly generated C NEF files."""
import argparse
import hashlib
from io import BytesIO
import json
from pathlib import Path

import numpy as np
import rawpy

from z62_nef_codec import inspect_nef


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--nef', type=Path, required=True)
    parser.add_argument('--expected-raw', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = {'schema': 1, 'completed': False, 'rawpy_version': rawpy.__version__,
              'libraw_version': list(rawpy.libraw_version), 'implementation_level': 'C',
              'factory_nef_equivalence_verified': False}
    try:
        data = args.nef.read_bytes()
        info = inspect_nef(data)
        require(info['bits'] == 14 and info['compression'] == 34713 and info['packed_fallback_excluded'],
                'Actual compressed14 NEF required, not a packed-size fallback')
        require(info['linearization'].startswith(b'F0\0\x08\0\x08\0\x08\0\x08'), 'F0/four2048 predictors required')
        expected = np.frombuffer(args.expected_raw.read_bytes(), dtype='<u2').reshape(info['height'], info['width'])
        with rawpy.imread(BytesIO(data)) as raw:
            decoded = raw.raw_image.copy()
            result.update(decoded_shape=list(decoded.shape), expected_shape=list(expected.shape),
                          black_levels=list(raw.black_level_per_channel), white_level=int(raw.white_level))
            equal = decoded.shape == expected.shape and np.array_equal(decoded, expected)
            require(equal, 'Independent decoded RAW samples differ from the acknowledged source')
            thumb = raw.extract_thumb()
            require(thumb.format == rawpy.ThumbFormat.JPEG, 'Independent decoder did not locate JPEG preview')
            expected_preview = data[info['preview_offset']:info['preview_offset'] + info['preview_bytes']]
            require(thumb.data == expected_preview, 'Extracted thumbnail differs from generated scene preview')
        result.update(completed=True, width=info['width'], height=info['height'], samples=int(expected.size),
                      every_raw_sample_equal=True, thumbnail_equal=True,
                      nef_sha256=hashlib.sha256(data).hexdigest(), raw_strip_bytes=info['raw_bytes'],
                      raw14_sha256=hashlib.sha256(expected.tobytes()).hexdigest(),
                      packed_fallback_excluded=True)
    except Exception as exc:
        result['failure'] = {'type': type(exc).__name__, 'message': str(exc)}
    with args.output.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['completed'] else 1)


if __name__ == '__main__':
    main()
