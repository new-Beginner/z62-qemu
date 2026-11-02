# SPDX-License-Identifier: GPL-2.0-or-later
"""Isolated Z62 timing experiment with explicit existing lab-source presets.
No physical USB, firmware patch, software state write or external IRQ injection.
Uses pinned staging; lab presets are hypotheses, never pixel/repair claims.
"""
import argparse
import hashlib
import importlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
from types import SimpleNamespace

from run_reference_console import ROOT, stage, install_native_process_adapter
from z62_capture_observation import PRESETS, observe_capture, install_preset

VERSION = '0.3.0'
STATUS_ADDRESS = 0xC253E0C0
OBSERVE_REGS = (0x20065508, 0x2006550C, 0x20065504, 0x20065400,
                0x20060044, 0x20060040, 0x20061000)


def health_complete(row):
    """Validate the entire bounded uint32 status observation; unknown is not clean."""
    codes, count = row.get('status_codes'), row.get('status_count')
    return (row.get('phase') == 'running' and not row.get('observation_error')
            and type(count) is int and 0 <= count <= 68
            and isinstance(codes, list) and len(codes) == count
            and all(type(code) is int and 0 <= code <= 0xffffffff for code in codes))


def observed_codes(row):
    """Partial facts remain visible, but malformed observations never pass health."""
    codes = row.get('status_codes')
    return codes if isinstance(codes, list) else []


def navigation_passed(row, changed):
    return (bool(changed) and row.get('phase') == 'running' and row.get('index') == 1
            and row.get('display_enabled') is True and row.get('queued') == []
            and health_complete(row) and row['status_codes'] == [])


def close_and_restore(machine, original, record):
    process = machine.process
    try:
        machine.close()
    except Exception as exc:
        record['cleanup_error'] = {'type': type(exc).__name__, 'message': str(exc)}
        record['menu_cycle_state_passed'] = False
    finally:
        subprocess.Popen = original
        try:
            record['process_closed'] = process is None or process.poll() is not None
        except Exception:
            record['process_closed'] = False
        if not record['process_closed']:
            record['menu_cycle_state_passed'] = False


def classify(samples):
    """Facts from samples only, not a causal proof or error-dialog classifier."""
    first_error = next((s for s in samples if 63 in observed_codes(s)), None)
    before_key = [s for s in samples if s['stage'] == 'before-menu']
    after_exit = [s for s in samples if s['stage'] == 'after-exit']
    reopened = any(s['stage'] == 'after-reopen' and s.get('index') == 1
                   and s.get('display_enabled') and not s.get('queued') for s in samples)
    running = [s for s in samples if s.get('phase') == 'running']
    health_known = bool(running) and all(health_complete(s) for s in running)
    return {
        'samples_before_menu': len(before_key),
        'observed_0x3f_before_menu': any(63 in observed_codes(s) for s in before_key),
        'first_0x3f': None if first_error is None else {
            k: first_error.get(k) for k in ('stage', 'virtual_seconds', 'wall_seconds', 'index', 'pending')},
        'menu_observed': any(s.get('index') == 1 and s.get('display_enabled') for s in samples),
        'reopened_observed': reopened,
        'left_menu_observed': any(s.get('index') == 3 for s in after_exit),
        'health_observations_complete': health_known,
        'all_status_lists_empty': health_known and all(s['status_codes'] == [] for s in running),
        'no_blocking_codes_observed': health_known and all(
            not any(0x3e <= c <= 0x44 for c in s['status_codes']) for s in running),
    }


def run(args):
    development = getattr(args, 'development_host', False)
    raw = getattr(args, 'functional_raw', False)
    if raw and not development:
        raise ValueError('functional RAW requires explicit development host')
    device_record = None
    if development:
        from run_z62_development import apply_console, configure_command, verify_functional_build
        device_record = verify_functional_build(args.qemu.resolve(), raw)
    args.output.mkdir(parents=True, exist_ok=False)
    work, identity = stage('z62', args.qemu, experimental_parameters=True, updates=True)
    if development:
        apply_console(work / 'source')
    identity.update(development_host=development, functional_raw=raw, functional_device=device_record)
    preset = getattr(args, 'capture_preset', 'baseline')
    identity['capture_preset'] = preset
    identity.update(experiment_version=VERSION, no_auto_menu=True, sampling_source=False,
                    main_screen_experiment=False, experimental_boundaries=0, sd_card=None)
    (args.output / 'session.json').write_text(json.dumps(identity, indent=2), encoding='utf-8')
    sys.path.insert(0, str(work / 'source'))
    module = importlib.import_module('tools.z62_console')
    original = install_native_process_adapter(work)
    subprocess.Popen = install_preset(subprocess.Popen, preset)
    if raw:
        parent = subprocess.Popen
        class RawPopen(parent):
            def __init__(self, command, *a, **kw):
                if isinstance(command, (list, tuple)) and 'qemu-system-arm' in str(command[0]):
                    command = configure_command(command, True)
                super().__init__(command, *a, **kw)
        subprocess.Popen = RawPopen
    config = SimpleNamespace(qemu=args.qemu.resolve(), master=work / 'inputs/master.bin',
        slave=work / 'inputs/slave.bin', controller=work / 'inputs/controller.bin',
        parameters=work / 'parameters', runs=work / 'runs', auto_menu=False,
        no_auto_menu=True, main_screen_experiment=False, sd_card=None, wsl=False,
        sampling_source=False, input_trace=True, update_store=work / 'update-store')
    machine = module.Z62Machine(config)
    record = {'version': VERSION, 'menu_at_virtual_seconds': args.menu_at,
              'no_guest_state_writes': True, 'camera_accessed': False,
              'snapshots_are_nonatomic': True, 'samples': [], 'keys': []}
    start = time.monotonic()

    def save():
        record['verdict'] = classify(record['samples'])
        (args.output / 'report.json').write_text(json.dumps(record, indent=2), encoding='utf-8')

    def observe(label):
        state = machine.status()
        if state['phase'] == 'failed' or state.get('error'):
            raise RuntimeError('console failure: ' + str(state.get('error')))
        row = {k: state.get(k) for k in ('phase', 'index', 'virtual_seconds', 'display_enabled',
                                        'queued', 'menu_pending', 'execution', 'lcd_frames')}
        row.update(stage=label, wall_seconds=round(time.monotonic()-start, 3))
        if development:
            row['functional_raw_status'] = state.get('functional_raw_status')
        if state['phase'] == 'running':
            with machine.io:
                try:
                    words = machine._words(STATUS_ADDRESS, 70)
                    count = words[68]
                    row['status_count'] = count
                    row['status_codes'] = words[:count] if count <= 68 else None
                    row['pending'] = hex(machine._words(0xC181DAE8, 1)[0])
                    row['mmio'] = {hex(a): hex(machine._words(a, 1)[0]) for a in OBSERVE_REGS}
                    row['capture'] = observe_capture(machine)
                except (RuntimeError, ValueError) as exc:
                    row['observation_error'] = str(exc)
        record['samples'].append(row)
        save()
        print(label, row.get('virtual_seconds'), row.get('index'), row.get('status_codes'), flush=True)
        return row

    def frame(label):
        path = args.output / (label + '.png')
        png = machine.frame_png()
        path.write_bytes(png)
        record.setdefault('frames', []).append({'label': label, 'sha256': hashlib.sha256(png).hexdigest()})
        save()

    def press(pin, label):
        record['keys'].append({'pin': pin, 'label': label,
                              'last_virtual_seconds': record['samples'][-1].get('virtual_seconds'),
                              'wall_seconds': round(time.monotonic()-start, 3)})
        save()
        machine.set_key(pin, 0)
        machine.set_key(pin, 1)

    def wait_until(label, predicate):
        while time.monotonic() - start < args.wall_limit:
            row = observe(label)
            if predicate(row):
                return row
            time.sleep(args.poll)
        raise TimeoutError('experiment wall limit exceeded: ' + label)

    try:
        machine.restart()
        row = wait_until('before-menu', lambda s: s.get('phase') == 'running'
                         and (s.get('virtual_seconds') or 0) >= args.menu_at)
        frame('before-menu')
        press(9, 'first-menu')
        sent = row['virtual_seconds']
        row = wait_until('after-first-menu', lambda s:
            (s.get('index') == 1 and s.get('display_enabled') and not s.get('queued'))
            or (s.get('virtual_seconds') or 0) >= sent + 12)
        frame('first-menu')
        if row.get('index') == 1:
            press(4, 'down')
            t = row['virtual_seconds']
            row = wait_until('menu-hold', lambda s: (s.get('virtual_seconds') or 0) >= t+3
                             and not s.get('queued'))
            frame('menu-down')
            record['cycles'] = []
            for cycle in range(args.cycles):
                suffix = '' if cycle == 0 else f'-{cycle+1}'
                press(getattr(args, 'exit_pin', 0), 'exit' + suffix)
                t = row['virtual_seconds']
                row = wait_until('after-exit', lambda s:
                    ((s.get('virtual_seconds') or 0) >= t+5 and s.get('index') == 3
                     and not s.get('queued')) or (s.get('virtual_seconds') or 0) >= t+args.exit_grace)
                dwell = getattr(args, 'post_exit_dwell', 0)
                if dwell > 0 and row.get('index') == 3:
                    dwell_start = row['virtual_seconds']
                    row = wait_until('after-exit', lambda s:
                        (s.get('virtual_seconds') or 0) >= dwell_start + dwell and not s.get('queued'))
                frame('after-exit' + suffix)
                item = {'cycle': cycle+1, 'returned_applv': row.get('index') == 3}
                record['cycles'].append(item)
                if not item['returned_applv']:
                    record['reopen_not_attempted'] = 'APPLV not reached within exit grace'
                    break
                press(9, 'reopen' + suffix)
                t = row['virtual_seconds']
                row = wait_until('after-reopen', lambda s: (s.get('virtual_seconds') or 0) >= t+6
                                 and not s.get('queued'))
                frame('after-reopen' + suffix)
                item['reopened'] = row.get('index') == 1 and row.get('display_enabled')
                if not item['reopened']:
                    break
                before = (args.output / ('after-reopen' + suffix + '.png')).read_bytes()
                press(4, 'reopen-down' + suffix)
                t = row['virtual_seconds']
                row = wait_until('reopen-navigation', lambda s:
                    (s.get('virtual_seconds') or 0) >= t+1.5 and not s.get('queued'))
                frame('reopen-down' + suffix)
                after = (args.output / ('reopen-down' + suffix + '.png')).read_bytes()
                from io import BytesIO
                from PIL import Image, ImageChops
                item['navigation_pixels_changed'] = ImageChops.difference(
                    Image.open(BytesIO(before)).convert('RGB'),
                    Image.open(BytesIO(after)).convert('RGB')).getbbox() is not None
                item['status_codes_after_navigation'] = row.get('status_codes')
                item['navigation_passed'] = navigation_passed(row, item['navigation_pixels_changed'])
                save()
                if not item['navigation_passed']:
                    break
        record['experiment_completed'] = True
        verdict = classify(record['samples'])
        record['menu_cycle_state_passed'] = all(verdict[k] for k in (
            'menu_observed', 'left_menu_observed', 'reopened_observed', 'all_status_lists_empty')) and (
            len(record.get('cycles', [])) == args.cycles and all(
                c.get('navigation_passed') for c in record.get('cycles', [])))
        record['visual_acceptance_required'] = True
    except Exception as exc:
        record['failure'] = {'type': type(exc).__name__, 'message': str(exc)}
        raise
    finally:
        try:
            if machine.phase == 'running':
                machine.release()
            if machine.work:
                for name in ('console.txt', 'command.json'):
                    p = machine.work / name
                    if p.exists():
                        shutil.copyfile(p, args.output / name)
        finally:
            close_and_restore(machine, original, record)
            try:
                for p in work.glob('effective-command-*.json'):
                    shutil.copyfile(p, args.output / p.name)
            finally:
                save()
    print(json.dumps(record['verdict']), flush=True)
    return record


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--qemu', type=Path, default=ROOT / '.build/z62-reference-2026.10.27-r1/runtime/qemu-system-arm.exe')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--capture-preset', choices=PRESETS, default='baseline')
    p.add_argument('--development-host', action='store_true')
    p.add_argument('--functional-raw', action='store_true')
    p.add_argument('--menu-at', type=float, default=20)
    p.add_argument('--poll', type=float, default=2)
    p.add_argument('--wall-limit', type=float, default=1200)
    p.add_argument('--cycles', type=int, default=1)
    p.add_argument('--exit-grace', type=float, default=15,
                   help='Virtual seconds allowed for APPIDLE to settle to APPLV')
    a = p.parse_args()
    if a.functional_raw and not a.development_host:
        p.error('--functional-raw requires --development-host')
    if a.menu_at < 3 or a.poll <= 0 or a.wall_limit <= 0 or a.exit_grace < 5 or not 1 <= a.cycles <= 10:
        p.error('menu-at >=3, exit-grace >=5, 1<=cycles<=10, poll and wall-limit >0 required')
    result = run(a)
    if not result.get('menu_cycle_state_passed'):
        raise SystemExit(1)
