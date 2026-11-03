"""Observe whether a real native RAW generation ceases after +0C bit200.

This is a firmware-free device check, not evidence of physical Nikon semantics.
"""
import argparse
import json
from pathlib import Path
import probe_z62_raw_stream as raw
from probe_z62_functional_raw import SLOTS, SIZE
import run_z62_statistics_observe as host


def check(binary):
    build = host.verify_build(binary)
    with raw.session(binary) as session:
        raw.start(session); session.fill(); raw.frame(session)
        before = raw.get(session, 'frames')
        if before != 1: raise ValueError('Initial real RAW generation did not complete')
        session.write(0x20068290, 0x100)
        session.fill()
        session.write(0x2006800c, 0x200)
        running = raw.get(session, 'active')
        raw.frame(session)
        after = raw.get(session, 'frames')
        preserved = all(session.read(address, SIZE) == b'\xa5'*SIZE for address in SLOTS)
        return {'schema': 1, 'completed_probe': True, 'qemu_sha256': build['binary_sha256'],
            'stop_address': '0x2006800c', 'stop_value': 0x200,
            'frames_before_stop': before, 'frames_after_stop_and_boundary': after,
            'raw_stream_active_after_stop': running, 'entire_four_raw_slots_preserved': preserved,
            'stop_request_honored': bool(not running and after == before and preserved),
            'guest_firmware_executed': False, 'physical_protocol_verified': False,
            'camera_accessed': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qemu', type=Path, default=host.DEFAULT_QEMU)
    parser.add_argument('--output', type=Path, required=True); parser.add_argument('--require-stop', action='store_true')
    args = parser.parse_args()
    if args.output.exists(): raise FileExistsError('Existing native evidence is immutable')
    try:
        record = check(args.qemu.resolve())
    except Exception as exc:
        record = {'schema': 1, 'completed_probe': False, 'failure': {'type': type(exc).__name__, 'message': str(exc)}}
    record['stop_acceptance_requested'] = args.require_stop
    with args.output.open('x', encoding='utf-8') as handle: json.dump(record, handle, indent=2)
    print(json.dumps(record), flush=True)
    raise SystemExit(0 if record['completed_probe'] and (not args.require_stop or record['stop_request_honored']) else 1)
