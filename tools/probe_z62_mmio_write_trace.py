"""Native log backend/absolute-address/repeated-write proof without firmware."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from unittest.mock import patch

import probe_z62_raw_stream as raw
import run_z62_raw_stop_control as host
from z62_mmio_write_trace import parse_lines

WRITES = ((0x20069a18, 1), (0x20069a18, 0), (0x20069a18, 1), (0x20069a18, 1),
          (0x20069518, 0x05ea0000), (0x20068100, 0x80), (0x2006800c, 0x200))


def check(output, binary):
    build = host.verify_build(binary); actual = []; readbacks = []
    with tempfile.TemporaryDirectory(prefix='z62-mmio-native-') as folder:
        folder = Path(folder)
        if not str(folder).isascii(): raise ValueError('Native trace requires ASCII log path')
        log = folder/'mmio-write.log'; prior = raw.subprocess.Popen
        def launch(command, *args, **kwargs):
            command = list(command)
            if Path(command[0]).resolve() == binary.resolve():
                if '-D' in command or '-trace' in command: raise ValueError('Trace/log option already present')
                command += ['-trace', 'enable=memory_region_ops_write', '-D', log.as_posix(), '-msg', 'timestamp=on']
                actual[:] = command
            return prior(command, *args, **kwargs)
        with patch.object(raw.subprocess, 'Popen', launch), raw.session(binary, False) as session:
            for address, value in WRITES:
                session.write(address, value)
                observed = raw.read(session, address)
                if observed != value: raise ValueError('Native register readback differs')
                readbacks.append({'address': hex(address), 'requested': value, 'actual': observed})
        if not log.is_file(): raise ValueError('Enabled trace backend did not create a log')
        if log.stat().st_size > 8*1024*1024: raise ValueError('Native trace exceeds its bounded budget')
        target = output/'mmio-write.log'; shutil.copyfile(log, target)
    data = target.read_bytes()
    rows = parse_lines(data.decode('utf-8').splitlines())
    selected = [r for r in rows if r['address'] in {a for a, _ in WRITES}]
    if [(r['address'], r['value']) for r in selected] != list(WRITES):
        raise ValueError('Actual native trace does not retain every ordered write')
    if any(r['cpu'] != -1 or r['board_view'] is not None or r['size'] != 4 for r in selected):
        raise ValueError('Unexpected QTest write attribution or size')
    return {'schema': 1, 'completed': True, 'qemu_sha256': build['binary_sha256'],
            'effective_command': actual, 'log_file': target.name, 'log_sha256': hashlib.sha256(data).hexdigest(),
            'log_bytes': len(data), 'events': rows, 'register_readbacks': readbacks,
            'absolute_addresses_verified': True, 'same_value_write_attempts_preserved': True,
            'qtest_cpu_view_remains_unknown': True, 'accepted_native_fixture_readbacks': True,
            'all_future_logged_writes_are_accepted': False, 'guest_firmware_executed': False,
            'trace_prefix_is_guest_virtual_time': False, 'camera_accessed': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qemu', type=Path, default=host.DEFAULT_QEMU); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); args.output.mkdir(parents=True, exist_ok=False)
    try: result = check(args.output, args.qemu.resolve())
    except Exception as exc: result = {'schema': 1, 'completed': False, 'failure': {'type': type(exc).__name__, 'message': str(exc)}}
    with (args.output/'native-mmio-check.json').open('x', encoding='utf-8') as handle: json.dump(result, handle, indent=2)
    print(json.dumps({'completed': result['completed'], 'failure': result.get('failure')}), flush=True)
    raise SystemExit(0 if result['completed'] else 1)
