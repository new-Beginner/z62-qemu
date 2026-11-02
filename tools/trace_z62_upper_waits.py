# SPDX-License-Identifier: GPL-2.0-or-later
"""Bounded Z62 C1.70/r1 upper-wait evidence; execution breakpoints, no guest patches.

Existing init-mode lab preset and synthetic parameters are explicit, not a repair.
Only this instance's process is closed. No HTTP listener or physical USB access.
"""
import argparse
from collections import Counter
import hashlib
import importlib
import json
from pathlib import Path
import re
import select
import shutil
import subprocess
import sys
import time
from types import SimpleNamespace

from run_reference_console import ROOT, stage, install_native_process_adapter
from z62_capture_observation import install_preset, observe_capture

MASTER_SHA = 'bb83613121f843d65101da936d942acdc513d86dbd3abc26259d0d870d03f5d4'
CONTROLLER_SHA = '9c65cad554ed02f83d37fbc825a8eb9efe79e3f32f98894dd5dd73edee416983'
R1_SHA = 'e169431ed0a24dded62c2d3e0ea2aba1056385ec96584c57b40cd4e5ab29fba4'
CALLS = (0x103999BA, 0x103999FC, 0x10399BD8, 0x1039C1F4, 0x1039C318)
POINTS = {a: 'wait-call' for a in CALLS}
POINTS.update({a + 4: 'wait-return' for a in CALLS})
POINTS.update({0x10397EC8: 'status-producer', 0x103970D4: 'status-append',
               0x10396B6A: 'notification', 0x10397E78: 'mode-request',
               0x10396EB6: 'notification-dispatch'})
MMIO = (0x20065508, 0x2006550C, 0x20065504, 0x20065400,
        0x20060044, 0x20060040, 0x20061000)
EXTRA_WORDS = {}
NOTIFICATIONS = {0x03030004}
POINT_ONCE = set()


def observe_with_timeout_evidence(snapshot, record, *, enabled, consecutive,
                                  gdb_ready, monitor_diagnostics, wall_seconds):
    """Keep the event loop available after a missing read, without replaying controls."""
    try:
        return snapshot(), 0
    except TimeoutError as exc:
        if not enabled:
            raise
        count = consecutive + 1
        entry = {'sequence': len(record.get('observation_timeouts', [])) + 1,
                 'wall_seconds': wall_seconds, 'consecutive': count,
                 'error': str(exc), 'gdb_packet_waiting': bool(gdb_ready()),
                 'monitor': monitor_diagnostics(), 'control_commands_replayed': False}
        record.setdefault('observation_timeouts', []).append(entry)
        print('OBSERVATION_TIMEOUT', json.dumps(entry), flush=True)
        if count >= 3:
            raise
        return None, count


def memory_watch_address(stop, active_watches, access='write'):
    if access not in ('read', 'write'):
        raise ValueError('Unknown memory observation type')
    marker = 'rwatch' if access == 'read' else 'watch'
    match = re.search(r'(?:^T05|;)' + marker + r':([0-9a-f]+);', stop)
    if match is None:
        return None
    address = int(match.group(1), 16)
    if address not in active_watches:
        raise RuntimeError('Unexpected memory observation address')
    return address


def step_suspended_watch_addresses(active_watches, watch_address, access):
    if access not in ('read', 'write') or watch_address not in active_watches:
        raise ValueError('Require an active memory observation and its access type')
    # One original instruction can touch several watched words (for example
    # STM with register writeback). Any remaining watch can re-trap that step.
    return list(active_watches)


def validate_single_step_reply(reply):
    if not isinstance(reply, str) or not reply.startswith('T05'):
        raise RuntimeError('unexpected single-step result: ' + str(reply))
    if re.search(r'(?:^T05|;)(?:watch|rwatch|awatch):', reply):
        raise RuntimeError('Single-step hit another memory observation; instruction completion unknown')


def write_watch_address(stop, active_watches):
    return memory_watch_address(stop, active_watches, 'write')


def validate_memory_watches(writes, reads, window):
    if writes and reads:
        raise ValueError('Read and write observations require separate runs')
    watches, access = (dict(reads), 'read') if reads else (dict(writes), 'write')
    if watches and window is not None:
        raise ValueError('Memory observations and call-frame windows require separate runs')
    for address, size in watches.items():
        if (not isinstance(address, int) or isinstance(address, bool) or
                not isinstance(size, int) or isinstance(size, bool) or size not in (1, 2, 4, 8)):
            raise ValueError('Memory observation requires integer address and bounded size')
        ranges = [(0xC0000000, 0xE0000000)]
        if access == 'read':
            # Observed physical statistics pool; cached aliases are already in
            # the original RAM range. Do not accept peripheral/ROM addresses.
            ranges.append((0x88000000, 0x8B000000))
        if address % size or not any(low <= address <= high-size for low, high in ranges):
            raise ValueError('Memory observation requires an aligned bounded RAM location')
    return watches, access


def verify_instructions(data):
    from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_MCLASS
    if hashlib.sha256(data).hexdigest() != MASTER_SHA:
        raise ValueError('Original C1.70 master hash mismatch')
    decoder = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
    controller = None
    controller_decoder = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_MCLASS)
    evidence = []
    for address in sorted(POINTS):
        if 0x08000000 <= address < 0x08080000:
            if controller is None:
                controller = (ROOT / 'artifacts/z62-reference-1.70/controller.bin').read_bytes()
                if hashlib.sha256(controller).hexdigest() != CONTROLLER_SHA:
                    raise ValueError('Original controller identity mismatch')
            offset = address - 0x08000000
            insn = next(controller_decoder.disasm(controller[offset:offset + 4], address))
        elif 0x10020000 <= address < 0x10020000 + len(data):
            offset = address - 0x10020000
            insn = next(decoder.disasm(data[offset:offset + 4], address))
        else:
            raise ValueError('Probe instruction outside original modules')
        if address in CALLS and (insn.mnemonic, insn.op_str) != ('bl', '#0x1035d43a'):
            raise ValueError('Wait call instruction mismatch')
        if address - 4 in CALLS and insn.mnemonic not in ('cbz', 'cbnz'):
            raise ValueError('Wait return instruction mismatch')
        anchor = {'pc': hex(address), 'bytes': insn.bytes.hex(),
                  'mnemonic': insn.mnemonic, 'operands': insn.op_str}
        if address < 0x10020000:
            anchor['module'] = 'controller'
        evidence.append(anchor)
    return evidence


def summarize(record):
    hits = record.get('hits', [])
    counts = Counter(h['label'] for h in hits)
    waits, pending = [], {}
    for hit in hits:
        reg = hit['registers']
        if hit['label'] == 'wait-call':
            pending[(hit['thread'], int(reg['pc'], 16) + 4, reg['sp'])] = hit
        elif hit['label'] == 'wait-return':
            entry = pending.pop((hit['thread'], int(reg['pc'], 16), reg['sp']), None)
            waits.append({'return_pc': reg['pc'], 'result': int(reg['r0'], 16),
                          'entry_hit': entry['sequence'] if entry else None,
                          'return_hit': hit['sequence'],
                          'virtual_duration': round(hit['state']['virtual_seconds'] -
                              entry['state']['virtual_seconds'], 6) if entry else None})
    return {'counts': dict(counts), 'waits': waits,
            'unreturned_waits': [h['sequence'] for h in pending.values()],
            'status35_callers': [h['registers']['lr'] for h in hits
                if h['label'] == 'status-producer' and h['registers']['r0'] == '0x2'],
            'notification_03030004_count': sum(h['label'] == 'notification' and
                h['registers']['r0'] == '0x3030004' for h in hits),
            'status35_sampled': any(0x35 in (s.get('status_codes') or [])
                                    for s in record.get('observations', []))}


def trace_complete(record):
    summary = summarize(record)
    failed_waits = [w for w in summary['waits']
                    if w['result'] == 0 and w['entry_hit'] is not None]
    return (bool(summary['status35_callers']) and summary['status35_sampled']
            and bool(failed_waits) and record.get('live_anchors_verified') is True
            and any(h['label'] == 'status-append' and h['registers']['r0'] == '0x35'
                    for h in record.get('hits', []))
            and record.get('process_closed') is True and record.get('detach') == 'OK'
            and not record.get('failure') and not record.get('cleanup_error'))


def run(args, *, observation_hook=None, hit_hook=None):
    if hashlib.sha256(args.qemu.read_bytes()).hexdigest() != R1_SHA:
        raise ValueError('Requires unchanged old r1 executable')
    anchors = verify_instructions((ROOT / 'artifacts/z62-reference-1.70/master.bin').read_bytes())
    window_plan = getattr(args, 'breakpoint_window', None)
    watches, watch_access = validate_memory_watches(
        getattr(args, 'write_watchpoints', None) or {},
        getattr(args, 'read_watchpoints', None) or {}, window_plan)
    window = None
    if window_plan is not None:
        from z62_breakpoint_window import BreakpointWindow
        window = BreakpointWindow(window_plan, POINTS)
    args.output.mkdir(parents=True, exist_ok=False)
    work, identity = stage('z62', args.qemu, experimental_parameters=True, updates=True)
    identity.update(capture_preset='init-mode', no_auto_menu=True, sampling_source=False,
                    main_screen_experiment=False, sd_card=None)
    (args.output / 'session.json').write_text(json.dumps(identity, indent=2), encoding='utf-8')
    (args.output / 'anchors.json').write_text(json.dumps(anchors, indent=2), encoding='utf-8')
    sys.path.insert(0, str(work / 'source'))
    z = importlib.import_module('tools.z62_console')
    Remote = importlib.import_module('analyze.qemu_display').Remote
    original = install_native_process_adapter(work)
    subprocess.Popen = install_preset(subprocess.Popen, 'init-mode')
    config = SimpleNamespace(qemu=args.qemu.resolve(), master=work/'inputs/master.bin',
        slave=work/'inputs/slave.bin', controller=work/'inputs/controller.bin',
        parameters=work/'parameters', runs=work/'runs', auto_menu=False, no_auto_menu=True,
        main_screen_experiment=False, sd_card=getattr(args, 'sd_card', None), wsl=False, sampling_source=False,
        input_trace=True, update_store=work/'update-store')
    machine = z.Z62Machine(config)
    record = {'version': '0.1.0', 'camera_accessed': False, 'guest_state_patched': False,
              'breakpoint_timing_perturbed': True, 'snapshots_nonatomic': True,
              'hits': [], 'observations': [], 'keys': [], 'skipped_notifications': {},
              'wall_limit': args.wall_limit, 'virtual_limit': args.virtual_limit,
              'max_stops': args.max_stops, 'menu_at': args.menu_at}
    if window is not None:
        record.update(breakpoint_window=window_plan, breakpoint_window_events=[],
                      breakpoint_window_active=False, window_skipped_hits=0)
    remote, running = None, False
    active = set()
    active_watches = set()
    record['write_watchpoints'] = {hex(a): n for a, n in watches.items()} if watch_access == 'write' else {}
    if watch_access == 'read':
        record['read_watchpoints'] = {hex(a): n for a, n in watches.items()}
    start = time.monotonic()
    phase, cycle, phase_start = 'before-menu', 0, 0
    first35 = None

    def save():
        record['summary'] = summarize(record)
        (args.output/'trace.json').write_text(json.dumps(record, indent=2), encoding='utf-8')

    def snapshot():
        s = machine.status()
        row = {k: s.get(k) for k in ('phase', 'index', 'virtual_seconds',
            'display_enabled', 'menu_pending', 'queued', 'execution')}
        row.update(stage=phase, cycle=cycle, wall_seconds=round(time.monotonic()-start, 3))
        with machine.io:
            words = machine._words(0xC253E0C0, 70)
            row['status_count'] = words[68]
            row['status_codes'] = words[:words[68]] if words[68] <= 68 else None
            row['pending'] = hex(machine._words(0xC181DAE8, 1)[0])
            row['upper_state'] = {hex(0xC1868290 + 4*i): hex(v)
                                 for i, v in enumerate(machine._words(0xC1868290, 40))}
            row['extra_words'] = {hex(address): [hex(v) for v in machine._words(address, count)]
                                  for address, count in EXTRA_WORDS.items()}
            row['mmio'] = {hex(a): hex(machine._words(a, 1)[0]) for a in MMIO}
            row['capture'] = observe_capture(machine)
        return row

    def arm(address):
        remote.breakpoint(address)
        active.add(address)

    def disarm(address):
        remote.breakpoint(address, False)
        active.remove(address)

    def set_watch(address, enabled):
        command = ('Z' if enabled else 'z') + ('3' if watch_access == 'read' else '2') + f',{address:x},{watches[address]:x}'
        if remote.command(command) != 'OK':
            raise RuntimeError('Cannot configure native memory observation: ' + command)
        if enabled:
            active_watches.add(address)
        else:
            active_watches.remove(address)

    def resume():
        nonlocal running
        remote.sock.sendall(b'$c#63')
        running = True
        if remote.sock.recv(1) != b'+':
            raise RuntimeError('missing continue acknowledgement')

    def press(pin, label, row):
        record['keys'].append({'pin': pin, 'label': label, 'cycle': cycle,
                              'virtual_seconds': row['virtual_seconds'],
                              'wall_seconds': round(time.monotonic()-start, 3)})
        machine.set_key(pin, 0)
        machine.set_key(pin, 1)
        print('KEY', label, row['virtual_seconds'], flush=True)

    try:
        machine.restart()
        while machine.phase not in ('running', 'failed'):
            if time.monotonic()-start > 60:
                raise TimeoutError('start timeout')
            time.sleep(.05)
        if machine.phase != 'running':
            raise RuntimeError(machine.error)
        record['pid'] = machine.process.pid
        # "running" means the QEMU process started, not that guest timer/RAM
        # initialization finished. Stopping it earlier leaves _key_clock at 0.
        while True:
            try:
                state = machine.status()
                if state.get('phase') != 'running' or state.get('error'):
                    raise RuntimeError('Guest failed before trace attachment')
                if state.get('virtual_seconds') is not None:
                    record['pre_attachment_virtual_seconds'] = state['virtual_seconds']
                    break
            except ValueError as exc:
                if str(exc) not in ('Input clock is unavailable', 'Could not read machine state'):
                    raise
            if time.monotonic() - start > min(60, args.wall_limit):
                raise TimeoutError('Guest observation clock did not initialize')
            time.sleep(.05)
        with machine.io:
            machine.qmp.command('stop')
        command = json.loads((machine.work/'command.json').read_text())
        port = int(command[command.index('-gdb')+1].rsplit(':', 1)[1])
        record['gdb_port'] = port
        remote = Remote(port)
        remote.select_thread(1)
        # Validate actual stopped guest instructions against immutable original member.
        for anchor in anchors:
            remote.select_thread(5 if anchor.get('module') == 'controller' else 1)
            expected = bytes.fromhex(anchor['bytes'])
            if remote.read(int(anchor['pc'], 16), len(expected)) != expected:
                raise ValueError('Live instruction mismatch at ' + anchor['pc'])
        remote.select_thread(1)
        record['live_anchors_verified'] = True
        record['attachment'] = snapshot()
        for address in POINTS:
            if window is None or window.should_arm(address):
                arm(address)
        for address in watches:
            set_watch(address, True)
        resume()
        next_observe, stops = 0, 0
        consecutive_observation_timeouts = 0
        recover_observation = bool(getattr(args, 'observation_timeout_recovery', False))
        record['observation_timeout_recovery_enabled'] = recover_observation
        while time.monotonic()-start < args.wall_limit and stops < args.max_stops:
            if select.select([remote.sock], [], [], .1)[0]:
                stop = remote.receive()
                running = False
                if not stop.startswith('T05'):
                    raise RuntimeError('Unexpected RSP stop: ' + stop)
                thread = re.search(r'thread:([0-9a-f]+)', stop).group(1)
                remote.select_thread(int(thread, 16))
                raw = remote.regs()
                reg = {n: remote.get(raw, n) for n in
                       ('pc', 'lr', 'sp', 'r0', 'r1', 'r2', 'r3', 'r4', 'r5', 'r6', 'r7')}
                pc = reg['pc']
                watch_address = memory_watch_address(stop, active_watches, watch_access)
                if watch_address is None and pc not in active:
                    raise RuntimeError(f'Unexpected PC {pc:#x}')
                stops += 1
                transition = window.transition(pc, reg, thread) if window is not None else None
                if window is not None and not window.includes(pc, reg, thread):
                    record['window_skipped_hits'] += 1
                elif pc == 0x10396B6A and reg['r0'] not in NOTIFICATIONS:
                    key = hex(reg['r0'])
                    record['skipped_notifications'][key] = record['skipped_notifications'].get(key, 0)+1
                else:
                    hit = {'sequence': len(record['hits'])+1,
                           'label': ('native-ram-' + watch_access) if watch_address is not None else POINTS[pc],
                           'thread': thread, 'stop': stop,
                           'registers': {k: hex(v) for k, v in reg.items()},
                           'state': snapshot(), 'stack_32': remote.read(reg['sp'], 32).hex()}
                    if watch_address is not None:
                        hit['watch_address'] = hex(watch_address)
                        hit['watch_before'] = remote.read(watch_address, watches[watch_address]).hex()
                        hit['watch_instruction_4'] = remote.read(pc, 4).hex()
                    if hit_hook is not None:
                        hit['extra_observation'] = hit_hook(remote, reg)
                    record['hits'].append(hit)
                    print('HIT', hit['sequence'], hit['label'], hex(pc), hex(reg['r0']),
                          hex(reg['lr']), hit['state']['virtual_seconds'], flush=True)
                    save()
                if transition is not None:
                    record['breakpoint_window_events'].append({'kind':transition,'pc':hex(pc),
                        'thread':thread,'sp':hex(reg['sp']),'after_hit':len(record['hits'])})
                    record['breakpoint_window_active'] = window.active
                    for address in sorted(window.scoped_points):
                        if transition == 'open' and address not in active:
                            arm(address)
                        elif transition == 'close' and address in active:
                            disarm(address)
                    save()
                # Step only the stopped CPU over the removed execution breakpoint.
                # Never write instructions, RAM, registers, or return values.
                suspended_watches = []
                if watch_address is not None:
                    # Memory observations may cover multiple operands or aliases.
                    # Suspend all watches for this one original instruction
                    # so another operand cannot recursively trap the step.
                    suspended_watches = step_suspended_watch_addresses(active_watches, watch_address, watch_access)
                    for address in suspended_watches:
                        set_watch(address, False)
                    hit['step_suspended_watches'] = [hex(a) for a in suspended_watches]
                else:
                    # An explicitly gated return was removed by its close transition.
                    if pc in active:
                        disarm(pc)
                if remote.command('Hc' + thread) != 'OK':
                    raise RuntimeError('cannot select step CPU')
                stepped = remote.command('s')
                validate_single_step_reply(stepped)
                if remote.command('Hc-1') != 'OK':
                    raise RuntimeError('cannot restore all-CPU continuation')
                if watch_address is not None:
                    hit['watch_after'] = remote.read(watch_address, watches[watch_address]).hex()
                    for address in suspended_watches:
                        set_watch(address, True)
                    save()
                elif pc not in POINT_ONCE and (window is None or window.should_arm(pc)):
                    arm(pc)
                resume()
            if running and time.monotonic() >= next_observe:
                row, consecutive_observation_timeouts = observe_with_timeout_evidence(
                    snapshot, record, enabled=recover_observation,
                    consecutive=consecutive_observation_timeouts,
                    gdb_ready=lambda: bool(select.select([remote.sock], [], [], 0)[0]),
                    monitor_diagnostics=lambda: machine.qmp.diagnostics()
                        if hasattr(machine.qmp, 'diagnostics') else {'available': False},
                    wall_seconds=round(time.monotonic()-start, 3))
                if row is None:
                    # Return to the RSP event loop before another fresh read:
                    # a target stop may have arrived during the QMP timeout.
                    save()
                    next_observe = time.monotonic() + args.poll
                    continue
                record['observations'].append(row)
                if observation_hook is not None:
                    experiment = observation_hook(machine, row)
                    if experiment is not None:
                        record.setdefault('device_experiments', []).append(experiment)
                now = row['virtual_seconds']
                print('STATE', phase, cycle, now, row['index'], row['status_codes'], flush=True)
                if 0x35 in (row['status_codes'] or []) and first35 is None:
                    first35 = now
                if first35 is not None and now >= first35 + 1:
                    record['stop_reason'] = 'status35 observed plus one virtual second'
                    break
                if now >= args.virtual_limit:
                    record['stop_reason'] = 'virtual limit'
                    break
                ready = not row['queued']
                if phase == 'before-menu' and now >= args.menu_at and row['index'] == 3:
                    press(9, 'first-menu', row)
                    phase, phase_start = 'after-first-menu', now
                elif phase == 'after-first-menu' and row['index'] == 1 and ready:
                    press(4, 'down', row)
                    phase, phase_start = 'menu-hold', now
                elif phase == 'menu-hold' and now >= phase_start+3 and ready:
                    cycle = 1
                    press(getattr(args, 'exit_pin', 0), 'exit-1', row)
                    phase, phase_start = 'after-exit', now
                elif phase == 'after-exit' and now >= phase_start+getattr(args, 'reopen_delay', 5) and row['index'] == 3 and ready:
                    press(9, 'reopen-' + str(cycle), row)
                    phase, phase_start = 'after-reopen', now
                elif phase == 'after-reopen' and now >= phase_start+6 and row['index'] == 1 and ready:
                    press(4, 'reopen-down-' + str(cycle), row)
                    phase, phase_start = 'reopen-navigation', now
                elif phase == 'reopen-navigation' and now >= phase_start+1.5 and ready:
                    if cycle >= 2:
                        record['stop_reason'] = 'two cycles finished without status35'
                        break
                    cycle += 1
                    press(getattr(args, 'exit_pin', 0), 'exit-' + str(cycle), row)
                    phase, phase_start = 'after-exit', now
                save()
                next_observe = time.monotonic()+args.poll
        else:
            record['stop_reason'] = 'wall or stop limit'
        record['stops'] = stops
    except Exception as exc:
        record['failure'] = {'type': type(exc).__name__, 'message': str(exc)}
        raise
    finally:
        if remote is not None:
            try:
                if running:
                    record['final_interrupt'] = remote.interrupt()
                for address in list(active):
                    disarm(address)
                for address in list(active_watches):
                    set_watch(address, False)
                record['detach'] = remote.command('D')
            except Exception as exc:
                record['cleanup_error'] = str(exc)
            finally:
                remote.sock.close()
        process = machine.process
        try:
            machine.close()
        except Exception as exc:
            record['cleanup_error'] = str(exc)
        finally:
            subprocess.Popen = original
            record['process_closed'] = process is None or process.poll() is not None
            if machine.work:
                for name in ('console.txt', 'command.json'):
                    source = machine.work/name
                    if source.exists():
                        shutil.copyfile(source, args.output/name)
            for source in work.glob('effective-command-*.json'):
                shutil.copyfile(source, args.output/source.name)
            record['trace_complete'] = trace_complete(record)
            save()
    return record


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--qemu', type=Path, default=ROOT/'.build/z62-reference-2026.10.27-r1/runtime/qemu-system-arm.exe')
    parser.add_argument('--menu-at', type=float, default=3)
    parser.add_argument('--poll', type=float, default=2)
    parser.add_argument('--wall-limit', type=float, default=900)
    parser.add_argument('--virtual-limit', type=float, default=45)
    parser.add_argument('--max-stops', type=int, default=2000)
    args = parser.parse_args()
    if min(args.poll, args.wall_limit, args.virtual_limit, args.max_stops) <= 0 or args.menu_at < 3:
        parser.error('positive limits and menu-at >=3 required')
    result = run(args)
    raise SystemExit(0 if trace_complete(result) else 1)
