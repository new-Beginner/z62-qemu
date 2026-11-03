"""Default-off, actual filtering, legacy-event equality and real DMA regression."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from unittest.mock import patch

import probe_z62_raw_stream as raw
import probe_z62_preview as preview
import probe_z62_raw_stop_control as model
from probe_z62_mmio_write_trace import WRITES
import run_z62_mmio_filter as host
import z62_mmio_write_trace as standard
import z62_mmio_filtered_trace as selected
from z62_mmio_filter_device import EVENT, WINDOWS

FIXTURE = (*WRITES, (0x20100420, 0x04000300), (0x20380048, 0x05ea03ee), (0x04264000, 0x21))
KEYS = ('cpu', 'region_pointer', 'address', 'value', 'size', 'region_name', 'board_view')


def check(output, binary):
    build = host.verify_build(binary)
    with raw.session(binary, False) as session:
        states = session.query('trace-event-get-state', {'name': EVENT})
        if len(states) != 1 or states[0]['state'] != 'disabled': raise ValueError('Selected event is not default-off')
    with tempfile.TemporaryDirectory(prefix='z62-filter-native-') as folder:
        folder = Path(folder)
        if not str(folder).isascii(): raise ValueError('Need ASCII native trace path')
        launched = []; prior = raw.subprocess.Popen
        def launch(command, *args, **kwargs):
            command = list(command)
            if Path(command[0]).resolve() == binary.resolve():
                if '-trace' in command or '-D' in command: raise ValueError('Unexpected prior trace options')
                path = folder/(str(len(launched))+'.log')
                command += ['-trace', 'enable='+EVENT, '-D', path.as_posix(), '-msg', 'timestamp=on']
                launched.append({'command': command, 'log': path})
            return prior(command, *args, **kwargs)
        checks = []
        with patch.object(raw.subprocess, 'Popen', launch):
            for both in (False, True):
                with preview.session(binary) as session:
                    entry = launched[-1]
                    if both: session.query('trace-event-set-state', {'name': standard.EVENT, 'enable': True})
                    if session.query('trace-event-get-state', {'name': EVENT})[0]['state'] != 'enabled':
                        raise ValueError('Selected event did not enable')
                    for address, value in FIXTURE:
                        session.write(address, value)
                        if raw.read(session, address) != value: raise ValueError('Model fixture readback changed')
                content = entry['log'].read_text(encoding='utf-8')
                fixture_log = output/('fixture-both.log' if both else 'fixture-selected.log')
                shutil.copyfile(entry['log'], fixture_log)
                std, picked = standard.parse_lines(content.splitlines()), selected.parse_lines(content.splitlines())
                expected = [(a, v) for a, v in FIXTURE if any(lo <= a < hi for lo, hi in WINDOWS)]
                diagnostic = {'both_events': both, 'expected_selected': [[hex(a), v] for a, v in expected],
                              'standard': std, 'selected': picked, 'fixture_log_sha256': hashlib.sha256(fixture_log.read_bytes()).hexdigest()}
                with (output/('fixture-both.json' if both else 'fixture-selected.json')).open('x', encoding='utf-8') as handle:
                    json.dump(diagnostic, handle, indent=2)
                if [(r['address'], r['value']) for r in picked] != expected:
                    raise ValueError('Selected backend emitted missing or out-of-window records')
                if both:
                    if [(r['address'], r['value']) for r in std] != list(FIXTURE): raise ValueError('Legacy event changed')
                    projected = [r for r in std if any(lo <= r['address'] < hi for lo, hi in WINDOWS)]
                    if [[r[k] for k in KEYS] for r in projected] != [[r[k] for k in KEYS] for r in picked]:
                        raise ValueError('Selected payload differs from legacy payload')
                elif std: raise ValueError('Unrequested standard event was emitted')
                checks.append({'both_events': both, 'standard_records': len(std), 'selected_records': len(picked),
                               'preview_device_mapped_for_fixture': True})
            regression = model.check(binary)
        logs = []
        for index, entry in enumerate(launched):
            if not entry['log'].exists(): continue
            target = output/(str(index)+'.log'); shutil.copyfile(entry['log'], target)
            logs.append({'file': target.name, 'sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
                         'bytes': target.stat().st_size, 'command': entry['command']})
    return {'schema': 1, 'completed': True, 'qemu_sha256': build['binary_sha256'], 'default_off': True,
        'fixture': [[hex(a), v] for a, v in FIXTURE], 'event_checks': checks, 'logs': logs,
        'selected_is_exact_legacy_projection_for_fixture': True, 'fixture_readbacks_unchanged': True,
        'actual_dma_stop_restart_regression_with_trace_on': regression,
        'guest_firmware_executed': False, 'camera_accessed': False, 'physical_protocol_verified': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qemu', type=Path, default=host.DEFAULT_QEMU); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); args.output.mkdir(parents=True, exist_ok=False)
    try: record = check(args.output, args.qemu.resolve())
    except Exception as exc: record = {'schema': 1, 'completed': False, 'failure': {'type': type(exc).__name__, 'message': str(exc)}}
    with (args.output/'native-filter-check.json').open('x', encoding='utf-8') as handle: json.dump(record, handle, indent=2)
    print(json.dumps({'completed': record['completed'], 'failure': record.get('failure')}), flush=True)
    raise SystemExit(0 if record['completed'] else 1)
