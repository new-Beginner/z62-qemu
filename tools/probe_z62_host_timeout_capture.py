"""Verify native host GDB attachment/detachment on an owned firmware-free QEMU."""
import argparse
import json
from pathlib import Path
from unittest.mock import patch

import z62_host_timeout_capture as capture
import probe_z62_raw_stream as raw
import run_z62_raw_stop_control as host


def check(output, binary):
    build = host.verify_build(binary); owned = []
    prior = capture.ORIGINAL_POPEN
    with capture.ascii_runtime(binary, build['binary_sha256']) as staged:
        def launch(command, *args, **kwargs):
            command = list(command)
            owned_command = Path(command[0]).resolve() == binary.resolve()
            if owned_command: command[0] = str(staged['binary'])
            process = prior(command, *args, **kwargs)
            if owned_command: owned.append(process)
            return process
        with patch.object(raw.subprocess, 'Popen', launch), raw.session(binary) as session:
            if len(owned) != 1: raise ValueError('Expected one retained QEMU process')
            process = owned[0]
            record = capture.capture(process, process.pid, staged['binary'], build['binary_sha256'], output/'host')
            if not record['completed_capture']: raise ValueError('Native host capture failed: '+json.dumps(record))
            if session.get('raw-stream-frames', session.master) != 0:
                raise ValueError('Host debugger changed the firmware-free frame source')
    return {'schema': 1, 'completed': True, 'capture': record,
            'native_firmware_free_probe': True, 'guest_firmware_executed': False,
            'ascii_runtime_file_sha256': staged['file_sha256'],
            'qmp_still_responds_after_detach': True, 'process_closed': process.poll() is not None,
            'camera_accessed': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True); parser.add_argument('--qemu', type=Path, default=host.DEFAULT_QEMU)
    args = parser.parse_args(); args.output.mkdir(parents=True, exist_ok=False)
    try: result = check(args.output, args.qemu.resolve())
    except Exception as exc: result = {'schema': 1, 'completed': False, 'failure': {'type': type(exc).__name__, 'message': str(exc)}}
    with (args.output/'native-host-check.json').open('x', encoding='utf-8') as handle: json.dump(result, handle, indent=2)
    print(json.dumps({'completed': result['completed'], 'failure': result.get('failure')}), flush=True)
    raise SystemExit(0 if result['completed'] else 1)
