"""r14 default-helper ablation: bounded original firmware, no injected calls."""
import argparse
import ctypes
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import threading
import time

import observe_model_baseline as baseline
from startup_contract import ROOT, PROFILES, require, read_inputs, sha
from observe_boot_wait import BootRemote, BootSession, build_command, sample
from observe_startup import free_port, connect
from observe_pool import quit_owned, close_handles
from verify_boot_wait import flags, EXPERIMENTAL, DEFAULT_COMPLETIONS
import z62_mmio_write_trace as trace_reader

TOOL = 'fenestra-z62-completion-ablation/0.1.0'
WORK = baseline.WORK
PROFILES_OFF = {'default': (), 'three-off': DEFAULT_COMPLETIONS,
                'gate-off': ('gate-completion',),
                'transfer-off': ('transfer-reset-completion',),
                'sequencer-off': ('sequencer-completion',)}
WINDOWS = [2, 15]
TRACE_LIMIT = 32 * 1024 * 1024
FALSE_FIELDS = baseline.FALSE_FIELDS + ('all_completion_logic_disabled', 'physical_protocol_equivalent')
SOURCES = baseline.SOURCES + ('fenestra/z62/observe_completion_ablation.py',
                              'tools/z62_mmio_write_trace.py')
REGIONS = {'gate': (0x04287000, 0x14), 'sequencer': (0x04251010, 0xC0),
           'transfer': (0x20100000, 0x24)}


def command(root, profile, ports, trace_path):
    require(profile in PROFILES_OFF, 'Unknown completion ablation profile')
    result = build_command(root, 'minimal', *ports)
    result[0] = str(root / WORK.relative_to(ROOT) / 'runtime/qemu-system-arm.exe')
    for name in PROFILES_OFF[profile]:
        result += ['-global', 'nikon-z72-boot-config.' + name + '=off']
    return result + ['-trace', 'enable=memory_region_ops_write', '-D', str(trace_path),
                     '-msg', 'timestamp=on']


def source_contract():
    path = WORK / 'source/qemu-10.2.4/hw/arm/nikon-z72.c'
    data = path.read_bytes()
    prepared = json.loads((WORK / 'prepared.json').read_text())
    require(sha(data) == prepared['source_sha256']['hw/arm/nikon-z72.c'], 'Compiled model source differs')
    text = data.decode('utf-8')
    for anchor in ('s->release_config && s->gate_completion &&',
                   's->master_role && s->sequencer_completion && size == 4',
                   'offset == 4 && value == 0 && s->transfer_reset_completion',
                   'Result word is read-only; zero is the success assumption.'):
        require(anchor in text, 'Completion source anchor differs')
    return {'source_sha256': sha(data), 'gate_command': '0x04287010 == 0xa1',
            'sequencer_commands': ['0x%08x' % (0x04251028 + i * 0x30) for i in range(4)],
            'transfer_reset': '0x20100004 == 0', 'other_success_assumptions_still_present': True}


def extra_registers(remote):
    result = {}
    for thread, role in ((1, 'master'), (3, 'slave')):
        remote.select_thread(thread)
        result[role] = {name: {'address': address, 'bytes': remote.read(address, size).hex()}
                        for name, (address, size) in REGIONS.items()}
    return result


def trace_summary(path):
    require(path.stat().st_size <= TRACE_LIMIT, 'Trace exceeded bounded size')
    events = []
    by_role = {}
    requests = {'gate': [], 'sequencer': [], 'transfer_reset': []}
    total = 0
    with path.open('r', encoding='utf-8') as handle:
        for line_number, line in enumerate(handle, 1):
            row = trace_reader.parse_line(line)
            if row is None:
                continue
            total += 1
            row['file_line'] = line_number
            role = row['board_view'] or 'unknown'
            by_role[role] = by_role.get(role, 0) + 1
            address, value = row['address'], row['value']
            kind = None
            if address == 0x04287010 and value == 0xA1:
                kind = 'gate'
            if address in [0x04251028 + i * 0x30 for i in range(4)] and value & 0x10000003 == 0x10000003:
                kind = 'sequencer'
            if address == 0x20100004 and value == 0:
                kind = 'transfer_reset'
            if kind:
                requests[kind].append(row)
    return {'trace_sha256': sha(path.read_bytes()), 'trace_bytes': path.stat().st_size,
            'attempted_mmio_writes': total, 'writes_by_role': by_role,
            'matching_request_attempts': requests, 'accepted_writes_proven': False,
            'all_helper_dependencies_exercised': False}


def check(record, output):
    require(record['tool'] == TOOL and record['completed'] is True and 'failure' not in record,
            'Incomplete ablation record')
    require(record['windows'] == WINDOWS and record['profile'] in PROFILES_OFF, 'Ablation bounds/profile differ')
    require(all(record[name] is False for name in FALSE_FIELDS) and record['firmware_inputs'] == PROFILES,
            'Ablation scope differs')
    build = json.loads((WORK / 'model-build.json').read_text())
    require(record['qemu_sha256'] == build['binary_sha256'] == sha((WORK / 'runtime/qemu-system-arm.exe').read_bytes()),
            'Ablation model identity differs')
    require(record['source_contract'] == source_contract() and
            record['sources'] == {n: sha((ROOT / n).read_bytes()) for n in SOURCES}, 'Ablation source differs')
    profile = record['profile']
    for name in DEFAULT_COMPLETIONS:
        expected = 'false' if name in PROFILES_OFF[profile] else 'true'
        require(flags(record['model_tree'], name) == [expected] * 2, 'Ablation property differs: ' + name)
    for name in EXPERIMENTAL:
        require(flags(record['model_tree'], name) == ['false'] * 2, 'Unrequested experimental helper')
    trace_path = Path('Q:/') / Path(output).resolve().relative_to(ROOT).with_suffix('.trace.log')
    require(record['command'] == command(Path('Q:/'), profile, record['ports'], trace_path), 'Ablation command differs')
    require(record['exit_code'] == 0 and record['quit_receipt']['acknowledged'] is True and
            record['owned_process_closed'] is True and record['mapping_removed'] is True and
            not record['close_notes'] and not record['trace_budget_exceeded'], 'Ablation cleanup/budget differs')
    require(len(record['samples']) == len(WINDOWS), 'Missing ablation sample')
    images, previous = read_inputs(), {}
    for seconds, point in zip(WINDOWS, record['samples']):
        require(point['requested_host_seconds'] == seconds and point['status']['running'] is False and
                point['stop'].startswith(('S02', 'T02')), 'Ablation window differs')
        require([c['role'] for c in point['cpus']] == ['master', 'master', 'slave', 'slave'], 'Ablation role layout differs')
        for i, cpu in enumerate(point['cpus']):
            require(cpu['image_head'] == images[cpu['role']][:0x6c].hex() and cpu['code']['matches_original'],
                    'Original ablation code differs')
            require(all(value == 0 for name, value in cpu['system'].items() if name.startswith(('DFSR', 'IFSR'))),
                    'Observed ablation fault register nonzero')
            ticks = cpu['model_clock_ticks']
            require(ticks >= previous.get(i, 0), 'Ablation clock reversed')
            previous[i] = ticks
        require(set(point['completion_registers']) == {'master', 'slave'}, 'Missing completion register sample')
        for values in point['completion_registers'].values():
            for name, (address, size) in REGIONS.items():
                require(values[name]['address'] == address and len(bytes.fromhex(values[name]['bytes'])) == size,
                        'Completion register window differs')
    for item in record['rsp_commands']:
        require(bool(item in ('g', 'c', 'qfThreadInfo') or item.startswith(('qSupported:', 'qXfer:features:read:')) or
                     re.fullmatch(r'Hg[0-9a-f]+|p[0-9a-f]+|m[0-9a-f]+,[0-9a-f]+', item)), 'Non-read-only ablation RSP')
    require(record['rsp_commands'].count('c') == 2 and record['rsp_controls'] == ['interrupt'] * 2,
            'Ablation continue/interrupt coverage differs')
    require(record['qmp_commands'] == [dict(command='qmp_capabilities', arguments={}),
            dict(command='human-monitor-command', arguments={'command-line': 'info qtree'}),
            dict(command='query-status', arguments={}), dict(command='query-status', arguments={}),
            dict(command='quit', arguments={})], 'Non-observation ablation QMP')
    require(record['trace'] == trace_summary(Path(output).with_suffix('.trace.log')), 'Ablation trace replay differs')
    return {'pid': record['owned_pid'], 'profile': profile, 'limited_ablation_observed': True,
            'last_model_seconds': {c['thread']: c['model_clock_ticks'] / 48000000
                                   for c in record['samples'][-1]['cpus']},
            'requests': {name: len(rows) for name, rows in record['trace']['matching_request_attempts'].items()},
            'complete_native_boot_verified': False, 'full_fenestra_port_verified': False,
            'all_completion_logic_disabled': False}


def run(output, profile):
    output = Path(output).resolve()
    require(profile in PROFILES_OFF, 'Unknown ablation profile')
    require(output.is_relative_to(ROOT / 'analysis/fenestra-z62-model-r14') and
            not any(output.with_suffix(suffix).exists() for suffix in ('.json', '.trace.log', '.qemu.log')),
            'Use new r14 ablation output')
    build = json.loads((WORK / 'model-build.json').read_text())
    require(build['binary_sha256'] == sha((WORK / 'runtime/qemu-system-arm.exe').read_bytes()), 'New model changed')
    images = read_inputs()
    record = {'tool': TOOL, 'created_at': datetime.now(timezone.utc).isoformat(),
              'profile': profile, 'windows': WINDOWS, 'completed': False, 'samples': [],
              'qemu_sha256': build['binary_sha256'], 'source_contract': source_contract(),
              'sources': {n: sha((ROOT / n).read_bytes()) for n in SOURCES}, 'firmware_inputs': PROFILES,
              **{name: False for name in FALSE_FIELDS}}
    buf = ctypes.create_unicode_buffer(32768)
    require(not ctypes.windll.kernel32.QueryDosDeviceW('Q:', buf, len(buf)), 'Q: occupied')
    require(not subprocess.check_output(['powershell.exe', '-NoProfile', '-Command',
        "Get-CimInstance Win32_Process -Filter \"name like 'qemu%'\" | Select-Object -ExpandProperty ProcessId"],
        encoding='utf-8').strip(), 'Existing QEMU process')
    process = remote = session = sock = stream = watcher = None
    budget = threading.Event()
    finished = threading.Event()
    error = None
    subprocess.run(['subst.exe', 'Q:', str(ROOT)], check=True)
    try:
        require(Path('Q:/').samefile(ROOT), 'Q: alias differs')
        ports = free_port(), free_port()
        trace_path = Path('Q:/') / output.relative_to(ROOT).with_suffix('.trace.log')
        cmd = command(Path('Q:/'), profile, ports, trace_path)
        record.update(command=cmd, ports=ports)
        with output.with_suffix('.qemu.log').open('xb') as log:
            process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=log,
                                       env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
        record['owned_pid'] = process.pid
        def watch():
            path = output.with_suffix('.trace.log')
            while not finished.wait(0.1):
                if path.exists() and path.stat().st_size > TRACE_LIMIT:
                    budget.set()
                    if process.poll() is None:
                        process.terminate()
                    return
        watcher = threading.Thread(target=watch, daemon=True)
        watcher.start()
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
        for seconds in WINDOWS:
            started = time.monotonic()
            remote.sock.settimeout(seconds)
            try:
                stop = remote.command('c')
            except socket.timeout:
                remote.sock.settimeout(15)
                stop = remote.interrupt()
            remote.sock.settimeout(15)
            status = session.query('query-status')
            require(status['running'] is False, 'Ablation CPUs not paused')
            record['samples'].append(dict(requested_host_seconds=seconds, stop=stop, status=status,
                elapsed_host_seconds=time.monotonic() - started, cpus=sample(remote, images),
                completion_registers=extra_registers(remote)))
        record['completed'] = True
    except Exception as exc:
        error = exc
        record['failure'] = type(exc).__name__ + ': ' + str(exc)
    finally:
        finished.set()
        if watcher is not None:
            watcher.join(timeout=2)
        record['trace_budget_exceeded'] = budget.is_set()
        if remote is not None:
            record.update(rsp_commands=remote.audit, rsp_controls=getattr(remote, 'controls', []))
        try:
            if process is not None and process.poll() is None and session is not None:
                record['quit_receipt'] = quit_owned(session, process)
        except Exception as exc:
            error = error or exc
            record['cleanup_error'] = str(exc)
        finally:
            if process is not None:
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=15)
                    record['forced_host_cleanup'] = True
                record.update(exit_code=process.returncode, owned_process_closed=process.poll() is not None)
            if session is not None:
                record['qmp_commands'] = session.audit
            record['close_notes'] = close_handles([getattr(remote, 'sock', None), stream, sock])
            subprocess.run(['subst.exe', 'Q:', '/D'], check=True)
            record['mapping_removed'] = not bool(ctypes.windll.kernel32.QueryDosDeviceW('Q:', buf, len(buf)))
            trace_path = output.with_suffix('.trace.log')
            if trace_path.exists() and trace_path.stat().st_size <= TRACE_LIMIT:
                record['trace'] = trace_summary(trace_path)
            with output.open('x', encoding='utf-8') as handle:
                json.dump(record, handle, indent=2)
    if error is not None:
        raise error
    return check(record, output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', choices=PROFILES_OFF, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.output, args.profile), indent=2))
