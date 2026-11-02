"""Extend the unchanged first capture experiment beyond the displayed 30s exposure."""
import argparse
import hashlib
import json
from pathlib import Path
import probe_z62_shutter_capture as parent


def run(output):
    original = parent.preview.run
    def extended(destination, duration, wall_limit, **kwargs):
        return original(destination, 90, 2400, **kwargs)
    parent.preview.run = extended
    try:
        result = parent.run(output)
    finally:
        parent.preview.run = original
    result['extended_observation'] = {
        'reason': '50s initial run ended only 29s after full press; display said 30s exposure',
        'requested_virtual_seconds': 90,
        'wrapper_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (output/'report.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    result = run(args.output)
    raise SystemExit(0 if result['observation_completed'] else 1)
