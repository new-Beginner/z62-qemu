"""Replay an actual r24 consumed source and validate a newly encoded NEF."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from z62_software_camera import SoftwareCamera, Scene
from z62_nef_codec import encode_nef, raw14_from_consumed_frame, inspect_nef

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipt', type=Path, default=ROOT / 'analysis/z62-camera-r24/release-flow-final/native-console-check.json')
    parser.add_argument('--decoder-python', type=Path, default=ROOT / '.build/tools/raw-verify-r25/Scripts/python.exe')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    receipt = json.loads(args.receipt.read_bytes())
    metadata = receipt['captured']['metadata']
    camera = SoftwareCamera(width=metadata['width'], height=metadata['height'], scene=Scene(),
                            clock_epoch=metadata['clock_epoch'])
    camera.event('power', {'on': True}, 0)
    camera.lens = deepcopy(metadata['lens'])
    camera.lens['moving'] = False
    camera.exposure = deepcopy(metadata['exposure'])
    frame = camera.frame(metadata['virtual_time_ns'])
    if frame.metadata['pixel_sha256'] != metadata['pixel_sha256']:
        raise ValueError('Original consumed source replay differs')
    frame.metadata = deepcopy(metadata)
    raw, updated = raw14_from_consumed_frame(frame)
    data = encode_nef(raw, frame.image, updated)
    info = inspect_nef(data)
    path = args.output / 'source-derived.NEF'
    path.write_bytes(data)
    expected = args.output / 'expected-raw14.bin'
    expected.write_bytes(raw.astype('<u2').tobytes())
    with (args.output / 'source.json').open('x', encoding='utf-8') as handle:
        json.dump({'source_receipt': str(args.receipt), 'source_receipt_sha256': hashlib.sha256(args.receipt.read_bytes()).hexdigest(),
                   'captured_source': updated, 'nef_sha256': hashlib.sha256(data).hexdigest(),
                   'raw_strip_bytes': info['raw_bytes'], 'packed_fallback_excluded': info['packed_fallback_excluded'],
                   'factory_capture_chain_verified': False}, handle, indent=2)
    result = subprocess.run([str(args.decoder_python), '-X', 'utf8', '-B', str(ROOT / 'tools/validate_z62_nef.py'),
        '--nef', str(path), '--expected-raw', str(expected), '--output', str(args.output / 'independent.json')],
        timeout=120)
    raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
