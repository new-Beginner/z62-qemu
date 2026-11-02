# SPDX-License-Identifier: GPL-2.0-or-later
"""Bounded candidate execution probe, not an assessment of firmware/flash safety.

--sentinel-self-test changes only staged master bytes to ARM mov r0,#0x62;
b . and verifies real CPU registers. No update container is written.
Run once per Python process to isolate the donor's Python module namespace.
"""
import argparse
import binascii
import importlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
from types import SimpleNamespace

import run_z62_transaction as host
import z62_candidate_firmware as inputs


def sentinel_candidate(original):
    files = dict(original.members)
    data = bytearray(files['master.bin'])
    data[:8] = bytes.fromhex('6200a0e3feffffea')  # ARM LE: mov r0,#98; b .
    data[-2:] = binascii.crc_hqx(data[:-2], 0).to_bytes(2, 'big')
    files['master.bin'] = bytes(data)
    info = original.metadata
    row = info['members']['master.bin']
    row.update(sha256=inputs.sha(data), matches_reference=False,
               changed_bytes=sum(a != b for a, b in zip(data, dict(original.members)['master.bin'])),
               first_changed_offset=0, last_changed_offset=len(data)-1)
    info.update(package=None, package_crc_verified=False,
                all_executed_members_match_reference=False,
                test_fixture='staged ARM sentinel; intentionally not camera firmware')
    return inputs.Candidate(tuple(sorted(files.items())), json.dumps(info))


def run(args):
    if args.output.exists():
        raise FileExistsError('Evidence directory already exists')
    candidate = inputs.load_candidate(package=(inputs.ROOT / inputs.SPEC['input'])
        if args.sentinel_self_test else args.firmware, members=args.members)
    if args.sentinel_self_test:
        candidate = sentinel_candidate(candidate)
    device = host.verify_build(args.qemu.resolve())
    args.output.mkdir(parents=True, exist_ok=False)
    report = {'schema': 1, 'probe_completed': False, 'firmware_health_verified': False,
              'flash_safety_verified': False, 'camera_accessed': False,
              'candidate': candidate.metadata, 'device': device, 'samples': []}
    old_path = list(sys.path)
    original_popen = subprocess.Popen
    machine, work, remote = None, None, None
    try:
        work, record = host.r4.base.stage('z62', args.qemu, experimental_parameters=True, updates=True)
        host.apply_console(work / 'source')
        inputs.install_candidate(work, record, candidate)
        inputs.apply_console(work / 'source', candidate)
        (args.output / 'session.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
        sys.path.insert(0, str(work / 'source'))
        module = importlib.import_module('tools.z62_console')
        host.r4.base.install_native_process_adapter(work)
        config = SimpleNamespace(qemu=args.qemu.resolve(), master=work/'inputs/master.bin',
            slave=work/'inputs/slave.bin', controller=work/'inputs/controller.bin',
            parameters=work/'parameters', runs=work/'runs', auto_menu=False, no_auto_menu=True,
            main_screen_experiment=False, sd_card=None, wsl=False, sampling_source=False,
            input_trace=True, update_store=work/'update-store')
        machine = module.Z62Machine(config)
        machine.restart()
        start = time.monotonic()
        while machine.phase not in ('running', 'failed'):
            if time.monotonic() - start > 60:
                raise TimeoutError('Candidate start timeout')
            time.sleep(.1)
        if machine.phase != 'running':
            raise RuntimeError(machine.error)
        report['pid'] = machine.process.pid
        deadline = time.monotonic() + args.wall_seconds
        while time.monotonic() < deadline:
            state = machine.status()
            with machine.io:
                state['qmp_execution'] = machine.qmp.command('query-status')
            report['samples'].append(state)
            if state.get('phase') != 'running' or state.get('error'):
                raise RuntimeError('Candidate QEMU stopped: ' + str(state.get('error')))
            if state.get('firmware_health_known') is not False:
                raise RuntimeError('Candidate health was incorrectly presented as known')
            if not state['qmp_execution'].get('running'):
                raise RuntimeError('QMP does not confirm a running guest')
            time.sleep(.5)
        with machine.io:
            machine.qmp.command('stop')
            command = json.loads((machine.work / 'command.json').read_text(encoding='utf-8'))
            port = int(command[command.index('-gdb')+1].rsplit(':', 1)[1])
            Remote = importlib.import_module('analyze.qemu_display').Remote
            remote = Remote(port)
            remote.select_thread(1)
            registers = remote.regs()
            report['master_cpu'] = {name: hex(remote.get(registers, name))
                                    for name in ('pc', 'r0', 'cpsr')}
            expected = dict(candidate.members)['master.bin'][:8]
            actual = remote.read(0x10020000, 8)
            report['entry_bytes'] = actual.hex()
            report['selected_entry_loaded'] = actual == expected
            if not report['selected_entry_loaded']:
                raise RuntimeError('QEMU did not load selected candidate bytes')
            if args.sentinel_self_test:
                report['sentinel_executed'] = (remote.get(registers, 'r0') == 0x62 and
                                               remote.get(registers, 'pc') == 0x10020004)
                if not report['sentinel_executed']:
                    raise RuntimeError('Modified ARM sentinel did not execute')
            report['detach'] = remote.command('D')
            if report['detach'] != 'OK':
                raise RuntimeError('GDB detach failed')
            remote.sock.close()
            remote = None
        (args.output / 'lcd.png').write_bytes(machine.frame_png())
        report['probe_completed'] = True
    except Exception as exc:
        report['failure'] = {'type': type(exc).__name__, 'message': str(exc)}
    finally:
        if remote is not None:
            remote.sock.close()
        if machine is not None:
            process = machine.process
            try:
                machine.close()
            except Exception as exc:
                report['cleanup_error'] = str(exc)
            report['qemu_exit_code'] = process.poll() if process is not None else None
            report['clean_exit'] = process is not None and process.poll() == 0
            if machine.work:
                for name in ('console.txt', 'command.json'):
                    if (machine.work / name).is_file():
                        shutil.copyfile(machine.work / name, args.output / name)
        subprocess.Popen = original_popen
        sys.path[:] = old_path
        if work is not None:
            report['staged_members_unchanged'] = all(
                inputs.sha((work / 'inputs' / name).read_bytes()) == inputs.sha(data)
                for name, data in candidate.members)
            for source in work.glob('effective-command-*.json'):
                shutil.copyfile(source, args.output / source.name)
        report['probe_completed'] = bool(report['probe_completed'] and report.get('clean_exit') and
            report.get('staged_members_unchanged') and not report.get('cleanup_error'))
        (args.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: report.get(k) for k in ('probe_completed', 'sentinel_executed',
        'master_cpu', 'clean_exit', 'failure', 'cleanup_error')}), flush=True)
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    choice = p.add_mutually_exclusive_group(required=True)
    choice.add_argument('--firmware', type=Path)
    choice.add_argument('--members', type=Path)
    choice.add_argument('--sentinel-self-test', action='store_true')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--qemu', type=Path, default=host.DEFAULT_QEMU)
    p.add_argument('--wall-seconds', type=float, default=10)
    args = p.parse_args()
    if not 1 <= args.wall_seconds <= 600:
        p.error('wall-seconds must be between 1 and 600')
    raise SystemExit(0 if run(args)['probe_completed'] else 1)


if __name__ == '__main__':
    main()
