"""Actual stop/no-new-DMA/restart checks plus default-off legacy behavior."""
import argparse
from contextlib import contextmanager
import json
from pathlib import Path
from unittest.mock import patch
import probe_z62_raw_stop_request as request
import probe_z62_raw_stream as raw
from probe_z62_functional_raw import SLOTS, SIZE
import run_z62_raw_stop_control as host


@contextmanager
def stop_option():
    prior = raw.host.configure_command
    def configure(command, *args, **kwargs):
        return prior(command, *args, **kwargs)+['-global', 'nikon-z72-boot-config.z62-raw-stop-control=on']
    with patch.object(raw.host, 'configure_command', configure): yield


def check(binary):
    build = host.verify_build(binary)
    legacy = request.check(binary)
    if legacy['stop_request_honored'] or legacy['frames_after_stop_and_boundary'] != 2:
        raise ValueError('Default-off r60 behavior changed')
    with stop_option():
        stopped = request.check(binary)
        if not stopped['stop_request_honored']: raise ValueError('RAW stop did not prevent real DMA')
        with raw.session(binary) as session:
            raw.start(session); session.fill(); raw.frame(session)
            for value in (0x10, 0x400, 0):
                session.write(0x20068290, 0x100)
                before = raw.get(session, 'frames')
                session.write(0x2006800c, value); raw.frame(session)
                if raw.get(session, 'frames') != before+1: raise ValueError('Unrelated stop bit halted RAW')
            session.write(0x20068290, 0x100)
            before = raw.get(session, 'frames'); session.fill()
            session.write(0x2006800c, 0x200); raw.frame(session); raw.frame(session)
            if raw.get(session, 'frames') != before or raw.get(session, 'active'):
                raise ValueError('Stopped RAW source still produced a generation')
            if not all(session.read(address, SIZE) == b'\xa5'*SIZE for address in SLOTS):
                raise ValueError('Stopped source changed RAW memory')
            session.write(0x20068008, 0x200); raw.frame(session)
            if raw.get(session, 'frames') != before+1 or not raw.get(session, 'active'):
                raise ValueError('Explicit RAW restart did not produce a fresh generation')
            session.verify_slots(raw.raw.raw.pattern(), guards=True)
        regression = raw.check(binary)
    return {'schema': 1, 'completed': True, 'qemu_sha256': build['binary_sha256'],
        'default_off_preserves_legacy': True, 'enabled_stop': stopped, 'unrelated_bits_do_not_stop': True,
        'stopped_boundaries_do_not_write_any_raw_slot': True, 'explicit_restart_real_dma': True,
        'raw_stream_regression': regression, 'guest_firmware_executed': False,
        'physical_protocol_equivalent': False, 'camera_accessed': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qemu', type=Path, default=host.DEFAULT_QEMU); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists(): raise FileExistsError('Existing native evidence is immutable')
    try: result = check(args.qemu.resolve())
    except Exception as exc: result = {'schema': 1, 'completed': False, 'failure': {'type': type(exc).__name__, 'message': str(exc)}}
    with args.output.open('x', encoding='utf-8') as handle: json.dump(result, handle, indent=2)
    print(json.dumps(result), flush=True)
    raise SystemExit(0 if result['completed'] else 1)
