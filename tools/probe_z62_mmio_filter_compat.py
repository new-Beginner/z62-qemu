"""Existing statistics/video suites on r64b with the selected trace enabled."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from unittest.mock import patch

import probe_z62_raw_stop_compat as suites
import probe_z62_raw_stream as raw
import run_z62_mmio_filter as host
from z62_mmio_filter_device import EVENT


def check(output, binary):
    build = host.verify_build(binary); launches = []; logs = []
    with tempfile.TemporaryDirectory(prefix='z62-filter-compat-') as folder:
        folder = Path(folder)
        if not str(folder).isascii(): raise ValueError('Need ASCII trace path')
        prior = raw.subprocess.Popen
        def launch(command, *args, **kwargs):
            command = list(command)
            if Path(command[0]).resolve() == binary.resolve():
                path = folder/(str(len(launches))+'.log')
                if '-trace' in command or '-D' in command: raise ValueError('Unexpected duplicate trace option')
                command += ['-trace', 'enable='+EVENT, '-D', path.as_posix(), '-msg', 'timestamp=on']
                launches.append({'command': command, 'path': path})
            return prior(command, *args, **kwargs)
        try:
            with patch.object(raw.subprocess, 'Popen', launch), patch.object(suites, 'host', host):
                result = suites.check(binary)
        finally:
            for index, entry in enumerate(launches):
                path = entry['path']
                if not path.exists(): continue
                target = output/(str(index)+'.log'); shutil.copyfile(path, target)
                logs.append({'file': target.name, 'bytes': target.stat().st_size,
                             'sha256': hashlib.sha256(target.read_bytes()).hexdigest(), 'command': entry['command']})
            with (output/'launches.json').open('x', encoding='utf-8') as handle: json.dump(logs, handle, indent=2)
    if result['completed'] is not True: raise ValueError('Existing native compatibility suite failed')
    return {'schema': 1, 'completed': True, 'qemu_sha256': build['binary_sha256'], 'event': EVENT,
            'stop_option_on': True, 'statistics_video': result, 'logs': logs,
            'guest_firmware_executed': False, 'camera_accessed': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qemu', type=Path, default=host.DEFAULT_QEMU); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); args.output.mkdir(parents=True, exist_ok=False)
    try: result = check(args.output, args.qemu.resolve())
    except Exception as exc: result = {'schema': 1, 'completed': False, 'failure': {'type': type(exc).__name__, 'message': str(exc)}}
    with (args.output/'native-compat-check.json').open('x', encoding='utf-8') as handle: json.dump(result, handle, indent=2)
    print(json.dumps({'completed': result['completed'], 'failure': result.get('failure')}), flush=True)
    raise SystemExit(0 if result['completed'] else 1)
