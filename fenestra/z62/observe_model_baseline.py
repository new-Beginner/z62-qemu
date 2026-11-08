"""r13 new-identity model baseline, not Fenestra or flashing acceptance."""
import argparse
import ctypes
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import time

from startup_contract import ROOT, PROFILES, require, read_inputs, sha
from observe_startup import free_port, connect
from observe_boot_wait import BootRemote, BootSession, build_command, sample
from observe_pool import quit_owned, close_handles
from verify_boot_wait import flags, EXPERIMENTAL, DEFAULT_COMPLETIONS

TOOL = 'fenestra-z62-model-baseline/0.1.0'
WORK = ROOT / '.build/fenestra-z62-model-r13-03'
FALSE_FIELDS = ('full_fenestra_port_verified', 'complete_native_boot_verified',
                'native_normal_shutdown_verified', 'flash_safety_verified',
                'old_r69_reproduced', 'camera_accessed', 'controller_loaded',
                'parameters_loaded', 'card_attached', 'debugger_guest_state_written')
SOURCES = ('fenestra/z62/observe_model_baseline.py', 'fenestra/z62/observe_boot_wait.py',
           'fenestra/z62/observe_pool.py', 'fenestra/z62/observe_startup.py',
           'fenestra/z62/startup_contract.py', 'fenestra/z62/pool_calls.py',
           'fenestra/z62/verify_boot_wait.py', 'tools/probe_z62_functional_raw.py',
           'third_party/z62-qemu/analyze/qemu_display.py', 'tools/probe_reference_devices.py')


def check_record(record):
    r = record
    build = json.loads((WORK / 'model-build.json').read_text(encoding='utf-8'))
    require(r['tool'] == TOOL and r['completed'] is True and 'failure' not in r,
            'Incomplete new-model baseline')
    require(r['build_manifest_sha256'] == sha((WORK / 'model-build.json').read_bytes()) and
            r['qemu_sha256'] == build['binary_sha256'] == sha((WORK / 'runtime/qemu-system-arm.exe').read_bytes()),
            'New model identity differs')
    require(r['sources'] == {n: sha((ROOT / n).read_bytes()) for n in SOURCES}, 'Baseline source differs')
    require(all(r[n] is False for n in FALSE_FIELDS) and r['firmware_inputs'] == PROFILES,
            'Baseline scope differs')
    require(r['exit_code'] == 0 and r['quit_receipt']['acknowledged'] is True and
            r['owned_process_closed'] is True and not r['close_notes'], 'Owned process cleanup differs')
    cmd = r['command']
    g = re.fullmatch(r'tcp:127\.0\.0\.1:([0-9]+)', cmd[15])
    q = re.fullmatch(r'tcp:127\.0\.0\.1:([0-9]+),server=on,wait=off', cmd[19])
    require(g is not None and q is not None, 'Loopback endpoints required')
    expected = build_command(Path('Q:/'), 'minimal', int(g[1]), int(q[1]))
    expected[0] = str(Path('Q:/') / WORK.relative_to(ROOT) / 'runtime/qemu-system-arm.exe')
    require(cmd == expected, 'Unexpected baseline command')
    for name in EXPERIMENTAL:
        require(flags(r['model_tree'], name) == ['false', 'false'], 'Unexpected opt-in: ' + name)
    for name in DEFAULT_COMPLETIONS:
        require(flags(r['model_tree'], name) == ['true', 'true'], 'Default completion differs: ' + name)
    require(len(r['samples']) == len(r['windows']) == 2, 'Missing baseline window')
    previous = {}
    images = read_inputs()
    for seconds, point in zip(r['windows'], r['samples']):
        require(point['requested_host_seconds'] == seconds and point['stop'].startswith(('T02', 'S02'))
                and point['status']['running'] is False and len(point['cpus']) == 4, 'Invalid paused sample')
        require([c['role'] for c in point['cpus']] == ['master', 'master', 'slave', 'slave'], 'Engine layout differs')
        for index, cpu in enumerate(point['cpus']):
            require(cpu['image_head'] == images[cpu['role']][:0x6c].hex() and
                    cpu['code']['matches_original'] is True, 'Original code identity differs')
            require(all(value == 0 for name, value in cpu['system'].items()
                        if name.startswith(('DFSR', 'IFSR'))), 'Observed fault register is nonzero')
            ticks = cpu['model_clock_ticks']
            require(ticks >= previous.get(index, 0), 'Non-monotonic model clock')
            previous[index] = ticks
    commands = r['rsp_commands']
    require(commands.count('c') == 2 and r['rsp_controls'] == ['interrupt'] * 2, 'Window control differs')
    for command in commands:
        require(bool(command in ('g', 'c', 'qfThreadInfo') or
                     command.startswith(('qSupported:', 'qXfer:features:read:')) or
                     re.fullmatch(r'Hg[0-9a-f]+|p[0-9a-f]+|m[0-9a-f]+,[0-9a-f]+', command)),
                'Non-read-only baseline command')
    return {'tool': TOOL, 'limited_original_baseline_verified': True,
            'pid': r['owned_pid'], 'qemu_sha256': r['qemu_sha256'],
            'last_model_seconds': {c['thread']: c['model_clock_ticks'] / 48000000
                                   for c in r['samples'][-1]['cpus']},
            'default_completion_logic_disabled': False,
            **{name: False for name in FALSE_FIELDS}}


def run(output, windows):
    output = Path(output).resolve()
    require(output.is_relative_to(ROOT / 'analysis/fenestra-z62-model-r13') and
            not output.exists() and not output.with_suffix('.qemu.log').exists(), 'Use new r13 output')
    require(len(windows) == 2 and all(1 <= n <= 30 for n in windows), 'Two bounded host windows required')
    build = json.loads((WORK / 'model-build.json').read_text(encoding='utf-8'))
    require(sha((WORK / 'runtime/qemu-system-arm.exe').read_bytes()) == build['binary_sha256'],
            'Built model identity differs')
    buf = ctypes.create_unicode_buffer(32768)
    require(not ctypes.windll.kernel32.QueryDosDeviceW('Q:', buf, len(buf)), 'Q: is occupied')
    require(not subprocess.check_output(['powershell.exe', '-NoProfile', '-Command',
        "Get-CimInstance Win32_Process -Filter \"name like 'qemu%'\" | Select-Object -ExpandProperty ProcessId"],
        encoding='utf-8').strip(), 'An existing QEMU is running')
    images = read_inputs()
    subprocess.run(['subst.exe', 'Q:', str(ROOT)], check=True)
    process = remote = session = stream = sock = None
    record = {'tool': TOOL, 'created_at': datetime.now(timezone.utc).isoformat(), 'completed': False,
              'windows': windows, 'samples': [], 'qemu_sha256': build['binary_sha256'],
              'build_manifest_sha256': sha((WORK / 'model-build.json').read_bytes()),
              'sources': {n: sha((ROOT / n).read_bytes()) for n in SOURCES}, 'firmware_inputs': PROFILES,
              'shutdown_scope': 'QMP quit is not native camera normal shutdown',
              **{name: False for name in FALSE_FIELDS}}
    failure = None
    try:
        require(Path('Q:/').samefile(ROOT), 'Workspace alias differs')
        ports = free_port(), free_port()
        command = build_command(Path('Q:/'), 'minimal', *ports)
        command[0] = str(Path('Q:/') / WORK.relative_to(ROOT) / 'runtime/qemu-system-arm.exe')
        record['command'] = command
        with output.with_suffix('.qemu.log').open('xb') as log:
            process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=log,
                                       env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
        record['owned_pid'] = process.pid
        sock = connect(ports[1], process)
        sock.settimeout(15)
        stream = sock.makefile('rwb')
        json.loads(stream.readline())
        session = BootSession()
        session.qmp = stream
        session.query('qmp_capabilities')
        remote = BootRemote(ports[0])
        record['threads'] = remote.command('qfThreadInfo')
        record['model_tree'] = session.query('human-monitor-command', {'command-line': 'info qtree'})
        for seconds in windows:
            remote.sock.settimeout(seconds)
            started = time.monotonic()
            try:
                stop = remote.command('c')
            except socket.timeout:
                remote.sock.settimeout(15)
                stop = remote.interrupt()
            remote.sock.settimeout(15)
            status = session.query('query-status')
            require(status['running'] is False, 'CPUs not paused')
            record['samples'].append({'requested_host_seconds': seconds, 'stop': stop, 'status': status,
                'elapsed_host_seconds': time.monotonic() - started, 'cpus': sample(remote, images)})
        record['completed'] = True
    except Exception as exc:
        failure = exc
        record['failure'] = type(exc).__name__ + ': ' + str(exc)
    finally:
        try:
            if remote is not None:
                record['rsp_commands'], record['rsp_controls'] = remote.audit, remote.controls
            if process is not None:
                if process.poll() is None and session is not None:
                    record['quit_receipt'] = quit_owned(session, process)
                if process.poll() is None:
                    # Only this retained Popen owner; no wildcard process cleanup.
                    process.terminate()
                    process.wait(timeout=15)
                    record['forced_host_cleanup'] = True
                record['exit_code'] = process.returncode
                record['owned_process_closed'] = process.poll() is not None
            if session is not None:
                record['qmp_commands'] = session.audit
        finally:
            record['close_notes'] = close_handles([getattr(remote, 'sock', None), stream, sock])
            subprocess.run(['subst.exe', 'Q:', '/D'], check=True)
            record['mapping_removed'] = not bool(ctypes.windll.kernel32.QueryDosDeviceW('Q:', buf, len(buf)))
            with output.open('x', encoding='utf-8') as handle:
                json.dump(record, handle, indent=2)
    if failure is not None:
        raise failure
    return check_record(record)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--windows', type=int, nargs=2, default=[2, 15])
    args = parser.parse_args()
    print(json.dumps(run(args.output, args.windows), indent=2))
