# SPDX-License-Identifier: GPL-2.0-or-later
"""Isolated r5 firmware A/B probe using the unchanged strict r4 cycle criteria.
Run one experiment per Python process. No physical camera or software-state writes.
"""
import argparse
import copy
import json
from pathlib import Path
import subprocess
import sys

import probe_z62_menu_timing as timing
import run_z62_transaction as host
from z62_development_status import functional_raw_status
from z62_transaction_status import transaction_status

VERSION = '0.1.0'


def run(args):
    if args.output.exists():
        raise FileExistsError('Refusing to alter existing experiment evidence: ' + str(args.output))
    if args.raw_completion and not args.functional_raw:
        raise ValueError('Completion requires functional RAW')
    device = host.verify_build(args.qemu.resolve())
    original_stage = timing.stage
    original_install = timing.install_native_process_adapter
    original_observe = timing.observe_capture
    original_popen = subprocess.Popen
    old_path = list(sys.path)
    metadata = dict(transaction_probe_version=VERSION, host_version=host.VERSION,
                    functional_raw=args.functional_raw, raw_completion=args.raw_completion,
                    transaction_device=device, no_guest_state_writes=True,
                    physical_camera_accessed=False, hardware_timing_verified=False)
    owned = False

    def stage(*a, **kw):
        nonlocal owned
        # Legacy run calls stage only after exclusive output-directory creation.
        owned = True
        work, record = original_stage(*a, **kw)
        host.apply_console(work / 'source')
        record.update(metadata)
        return work, record

    def install(work):
        previous = original_install(work)
        parent = subprocess.Popen
        class TransactionPopen(parent):
            def __init__(self, command, *a, **kw):
                if isinstance(command, (list, tuple)) and 'qemu-system-arm' in str(command[0]):
                    command = host.configure_command(command, args.functional_raw, args.raw_completion)
                super().__init__(command, *a, **kw)
        subprocess.Popen = TransactionPopen
        return previous

    def observe(machine):
        result = original_observe(machine)
        result.update(functional_raw_status(machine))
        result.update(transaction_status(machine))
        return result

    # Use explicit adapters only in this process; never modify the legacy tool on disk.
    timing.stage, timing.install_native_process_adapter, timing.observe_capture = stage, install, observe
    legacy_args = copy.copy(args)
    legacy_args.development_host = False
    legacy_args.functional_raw = False  # handled above; avoid legacy launcher adaptation twice
    result = None
    try:
        result = timing.run(legacy_args)
        result.update(metadata)
        return result
    finally:
        timing.stage, timing.install_native_process_adapter = original_stage, original_install
        timing.observe_capture = original_observe
        subprocess.Popen = original_popen
        sys.path[:] = old_path
        if owned:
            path = args.output / 'report.json'
            if result is not None:
                path.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
            elif path.is_file():
                partial = json.loads(path.read_text(encoding='utf-8'))
                partial.update(metadata)
                path.write_text(json.dumps(partial, indent=2) + '\n', encoding='utf-8')
            session = args.output / 'session.json'
            if session.is_file():
                identity = json.loads(session.read_text(encoding='utf-8'))
                identity.update(metadata)
                session.write_text(json.dumps(identity, indent=2) + '\n', encoding='utf-8')


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--version', action='version', version=VERSION)
    p.add_argument('--qemu', type=Path, default=host.DEFAULT_QEMU)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--capture-preset', choices=host.PRESETS, default='baseline')
    p.add_argument('--functional-raw', action='store_true')
    p.add_argument('--raw-completion', action='store_true')
    p.add_argument('--menu-at', type=float, default=3)
    p.add_argument('--poll', type=float, default=2)
    p.add_argument('--wall-limit', type=float, default=1800)
    p.add_argument('--cycles', type=int, default=3)
    p.add_argument('--exit-grace', type=float, default=15)
    args = p.parse_args(argv)
    if args.raw_completion and not args.functional_raw:
        p.error('--raw-completion requires --functional-raw')
    if args.menu_at < 3 or args.poll <= 0 or args.wall_limit <= 0 or args.exit_grace < 5 or not 1 <= args.cycles <= 10:
        p.error('menu-at >=3, exit-grace >=5, 1<=cycles<=10, poll and wall-limit >0 required')
    return args


if __name__ == '__main__':
    result = run(parse_args())
    if not result.get('menu_cycle_state_passed'):
        raise SystemExit(1)
