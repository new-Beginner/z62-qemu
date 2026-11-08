"""Bounded read-only stock Z62 boot-wait diagnostics; NOT a Fenestra integration test."""
import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import socket
import struct
import subprocess
import time

from startup_contract import ROOT, BASE, PROFILES, read_inputs, require, sha, arm_literal
from pool_calls import REGISTERS, SYSTEM
from observe_startup import QEMU_REL, QEMU_SHA, Session, free_port, connect
from observe_pool import ReadOnlyRemote, quit_owned, close_handles

TOOL = 'fenestra-z62-boot-wait/0.1.1'
CONTROLLER_SHA = '9c65cad554ed02f83d37fbc825a8eb9efe79e3f32f98894dd5dd73edee416983'
SOURCES = ('fenestra/z62/observe_boot_wait.py', 'fenestra/z62/observe_pool.py',
           'fenestra/z62/observe_startup.py', 'fenestra/z62/startup_contract.py',
           'fenestra/z62/pool_calls.py', 'third_party/z62-qemu/analyze/qemu_display.py',
           'tools/probe_reference_devices.py', 'tools/probe_z62_functional_raw.py')
FALSE_FIELDS = ('firmware_integrated', 'flash_safety_verified', 'camera_accessed',
                'debugger_guest_registers_written', 'debugger_guest_memory_written',
                'original_firmware_patched', 'injected_calls', 'parameters_loaded',
                'card_attached', 'laboratory_completion_enabled', 'frame_sync_enabled',
                'native_startup_completed', 'normal_shutdown_verified',
                'allocator_lifetime_verified', 'exact_model_source_recovered',
                'default_model_completion_logic_disabled')


def check_windows(values):
    values = [float(v) for v in values]
    require(1 <= len(values) <= 4 and all(math.isfinite(v) and 0 < v <= 60 for v in values)
            and sum(values) <= 120, 'Invalid bounded run windows')
    return values


def build_command(root, profile, gdb_port, qmp_port):
    require(profile in ('minimal', 'controller', 'controller-link'), 'Unknown boot profile')
    require(gdb_port != qmp_port, 'Port collision')
    machine = ('nikon-z62-dual-lab,'
               f'master-boot-image={root}/artifacts/z62-reference-1.70/master.bin,'
               f'slave-boot-image={root}/artifacts/z62-reference-1.70/slave.bin')
    if profile != 'minimal':
        machine += f',controller-firmware={root}/artifacts/z62-reference-1.70/controller.bin'
    if profile == 'controller-link':
        machine += ',controller-link=on'
    cmd = [str(root / QEMU_REL), '-M', machine, '-smp', '4,maxcpus=5', '-S',
           '-display', 'none', '-serial', 'none', '-monitor', 'none', '-nic', 'none',
           '-gdb', f'tcp:127.0.0.1:{gdb_port}', '-icount', 'shift=0,sleep=off',
           '-qmp', f'tcp:127.0.0.1:{qmp_port},server=on,wait=off']
    for cpu in range(4):
        cmd += ['-device', f'loader,addr={BASE:#x},cpu-num={cpu}']
    return cmd


class BootRemote(ReadOnlyRemote):
    def interrupt(self):
        if not hasattr(self, 'controls'):
            self.controls = []
        self.controls.append('interrupt')
        return super().interrupt()


class BootSession(Session):
    def query(self, command, arguments=None, error=False):
        allowed = command in ('query-status', 'query-cpus-fast', 'qmp_capabilities', 'quit')
        if command == 'human-monitor-command':
            allowed = arguments in ({'command-line': 'info cpus'}, {'command-line': 'info qtree'},
                                     {'command-line': 'info registers -a'})
        require(allowed and not error, 'Forbidden QMP command')
        if not hasattr(self, 'audit'):
            self.audit = []
        self.audit.append(dict(command=command, arguments=arguments or {}))
        return super().query(command, arguments, error)


def decode(raw, address, thumb):
    from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_THUMB
    return [dict(address=i.address, bytes=i.bytes.hex(), mnemonic=i.mnemonic, operands=i.op_str)
            for i in Cs(CS_ARCH_ARM, CS_MODE_THUMB if thumb else CS_MODE_ARM).disasm(raw, address)]


def code_window(image, pc, thumb, raw):
    address = pc - 16
    offset = address - BASE
    require(offset >= 0 and offset + 64 <= len(image) - 2, 'PC window outside original member')
    require(raw == image[offset:offset + 64], 'Runtime ROM differs from original')
    return dict(address=address, bytes=raw.hex(), matches_original=True,
                from_pc=decode(raw[16:], pc, thumb))


def scheduler_points(image, role):
    loop = {'master': 0x10107060, 'slave': 0x10038A34}[role]
    offset = loop - BASE
    require(image[offset:offset + 8] == bytes.fromhex('b09f10ee039009e2'),
            'Scheduler CPU-index anchor changed')
    require(image[offset + 16:offset + 32] == bytes.fromhex('93f021e3008095e5000058e30300000a'),
            'Scheduler idle-test anchor changed')
    return dict(loop=loop, current=arm_literal(image, offset - 0x2C, 4),
                ready=arm_literal(image, offset + 8, 5),
                system_stack=arm_literal(image, offset - 0x1C, 13))


def sample(remote, images):
    cpus = []
    for tid in range(1, 5):
        remote.select_thread(tid)
        data = remote.regs()
        regs = {n: remote.get(data, n) for n in REGISTERS}
        head = remote.read(BASE, 0x6C)
        roles = [r for r, image in images.items() if head == image[:0x6C]]
        require(len(roles) == 1, 'Engine CPU image identity missing')
        role, pc, sp = roles[0], regs['pc'], regs['sp']
        image = images[role]
        row = dict(thread=f'{tid:02x}', role=role, registers=regs,
                   system={n: remote.read_register(n) for n in SYSTEM}, image_head=head.hex())
        points = scheduler_points(image, role)
        row['scheduler'] = dict(points=points,
            current=list(struct.unpack('<2I', remote.read(points['current'], 8))),
            ready=list(struct.unpack('<2I', remote.read(points['ready'], 8))))
        row['model_clock_ticks'] = int.from_bytes(remote.read(0x04266008, 8), 'little')
        if BASE + 16 <= pc <= BASE + len(image) - 50:
            row['code'] = code_window(image, pc, bool(regs['cpsr'] & 32), remote.read(pc - 16, 64))
        else:
            row['code'] = dict(matches_original=False, reason='PC outside bounded original member window')
        if sp % 4 == 0 and 0xC1000000 <= sp <= 0xC8000000 - 128:
            row['stack'] = dict(address=sp, words=list(struct.unpack('<32I', remote.read(sp, 128))))
        else:
            row['stack'] = dict(address=sp, reason='SP outside bounded engine RAM window')
        cpus.append(row)
    require([c['role'] for c in cpus] == ['master', 'master', 'slave', 'slave'],
            'Unexpected engine CPU role layout')
    return cpus


def run(output, profile='minimal', windows=(1, 5, 15)):
    output = output.resolve()
    require(output.is_relative_to(ROOT / 'analysis') and not output.exists(), 'Use new analysis output')
    windows = check_windows(windows)
    root = Path('Q:/')
    require(root.is_dir() and root.samefile(ROOT), 'Verified Q: workspace alias required')
    binary = root / QEMU_REL
    require(sha(binary.read_bytes()) == QEMU_SHA, 'Pinned QEMU changed')
    images = read_inputs()
    controller = ROOT / 'artifacts/z62-reference-1.70/controller.bin'
    require(controller.stat().st_size == 524290 and sha(controller.read_bytes()) == CONTROLLER_SHA,
            'Requires original controller')
    ports = free_port(), free_port()
    command = build_command(root, profile, *ports)
    record = dict(schema=1, tool=TOOL, created_at=datetime.now(timezone.utc).isoformat(),
                  profile=profile, windows=windows, command=command, qemu_sha256=QEMU_SHA,
                  sources={n: sha((ROOT / n).read_bytes()) for n in SOURCES}, inputs=PROFILES,
                  controller_sha256=CONTROLLER_SHA, controller_loaded=profile != 'minimal',
                  controller_link_enabled=profile == 'controller-link',
                  firmware_loaded=True, reset_pc_initialized_by_qemu_loader=True,
                  observation_pauses_perturb_timing=True, completed=False,
                  owned_shutdown='QMP quit; NOT camera normal shutdown', samples=[],
                  **{n: False for n in FALSE_FIELDS})
    output.parent.mkdir(parents=True, exist_ok=True)
    log_path = output.with_suffix('.qemu.log')
    require(not log_path.exists(), 'Log already exists')
    process = remote = session = qmp_sock = qmp_stream = None
    failure = None
    with output.open('x', encoding='utf-8') as evidence:
        try:
            env = dict(os.environ, TEMP=os.environ['PI_SCRATCH_DIR'], TMP=os.environ['PI_SCRATCH_DIR'],
                       TMPDIR=os.environ['PI_SCRATCH_DIR'], PYTHONDONTWRITEBYTECODE='1')
            with log_path.open('xb') as log:
                process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=log, env=env)
            record['owned_pid'] = process.pid
            qmp_sock = connect(ports[1], process)
            qmp_sock.settimeout(15)
            qmp_stream = qmp_sock.makefile('rwb')
            session = BootSession()
            session.qmp = qmp_stream
            json.loads(qmp_stream.readline())
            session.query('qmp_capabilities')
            remote = BootRemote(ports[0])
            record['gdb_threads'] = remote.command('qfThreadInfo')
            record['model_tree'] = session.query('human-monitor-command', {'command-line': 'info qtree'})
            for seconds in windows:
                remote.sock.settimeout(seconds)
                started = time.monotonic()
                interrupted = False
                try:
                    stop = remote.command('c')
                except socket.timeout:
                    remote.sock.settimeout(15)
                    interrupted = True
                    stop = remote.interrupt()
                remote.sock.settimeout(15)
                require(stop.startswith(('T02', 'S02', 'T05', 'S05')), 'Unexpected debugger stop: ' + stop)
                elapsed = time.monotonic() - started
                status = session.query('query-status')
                require(status['running'] is False, 'Snapshot requires stopped CPUs')
                cpus = sample(remote, images)
                record['samples'].append(dict(requested_host_seconds=seconds, elapsed_host_seconds=elapsed,
                    stop=stop, interrupted=interrupted, status=status, cpus=cpus,
                    qmp_cpus=session.query('query-cpus-fast'),
                    cpu_summary=session.query('human-monitor-command', {'command-line': 'info cpus'}),
                    all_cpu_registers=session.query('human-monitor-command', {'command-line': 'info registers -a'})))
                print(profile, 'sample', len(record['samples']),
                      [(c['role'], c['thread'], hex(c['registers']['pc'])) for c in cpus], flush=True)
            record['completed'] = True
        except Exception as exc:
            failure = exc
            record['failure'] = type(exc).__name__ + ': ' + str(exc)
        finally:
            if remote is not None:
                record['rsp_commands'] = getattr(remote, 'audit', [])
                record['rsp_controls'] = getattr(remote, 'controls', [])
            if process is not None:
                try:
                    if process.poll() is None and session is not None:
                        record['quit_receipt'] = quit_owned(session, process)
                    record['exit_code'] = process.poll()
                    record['owned_process_closed'] = process.poll() is not None
                except Exception as exc:
                    record['cleanup_failure'] = type(exc).__name__ + ': ' + str(exc)
                    record['completed'] = False
                    failure = failure or exc
            if session is not None:
                record['qmp_commands'] = getattr(session, 'audit', [])
            record['close_notes'] = close_handles([getattr(remote, 'sock', None), qmp_stream, qmp_sock])
            record['qemu_log_sha256'] = sha(log_path.read_bytes()) if log_path.exists() else None
            json.dump(record, evidence, indent=2)
            evidence.write('\n')
    if failure is not None:
        raise failure
    require(record.get('exit_code') == 0 and record.get('owned_process_closed'), 'Owned process did not exit cleanly')
    return record


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--profile', choices=('minimal', 'controller', 'controller-link'), default='minimal')
    parser.add_argument('--windows', type=float, nargs='+', default=[1, 5, 15])
    args = parser.parse_args()
    run(args.output, args.profile, args.windows)
