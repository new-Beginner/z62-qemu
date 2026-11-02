# SPDX-License-Identifier: GPL-2.0-or-later
"""Compare optional r6 CAPCOM completion using the strict original cycle probe."""
import argparse
import json
from pathlib import Path
import sys

import probe_z62_transaction_cycle as cycle
import run_z62_capcom as capcom
from z62_capcom_status import capcom_status


def run(args):
    if args.output.exists():
        raise FileExistsError('Existing experiment evidence is protected')
    manifest = capcom.verify_build(args.qemu.resolve())
    original_config = cycle.host.configure_command
    original_observe = cycle.timing.observe_capture
    original_stage = cycle.timing.stage
    owned = False
    def stage(*a, **kw):
        nonlocal owned
        # The underlying probe creates the output directory exclusively before
        # calling stage. Never modify evidence if it rejected an existing path.
        owned = True
        work, record = original_stage(*a, **kw)
        record.update(capcom_sync=args.capcom_sync, capcom_device=manifest)
        return work, record
    def configure(command, raw=False, completion=False):
        return capcom.configure_command(original_config(command, raw, completion), args.capcom_sync)
    def observe(machine):
        value = original_observe(machine)
        value.update(capcom_status(machine))
        return value
    cycle.host.configure_command = configure
    cycle.timing.observe_capture = observe
    cycle.timing.stage = stage
    try:
        return cycle.run(args)
    finally:
        cycle.host.configure_command = original_config
        cycle.timing.observe_capture = original_observe
        cycle.timing.stage = original_stage
        for name in ('report.json', 'session.json'):
            path = args.output / name
            if owned and path.is_file():
                record = json.loads(path.read_text(encoding='utf-8'))
                record.update(capcom_sync=args.capcom_sync, capcom_device=manifest)
                path.write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__, add_help=False)
    p.add_argument('--capcom-sync', action='store_true')
    own, rest = p.parse_known_args()
    if '--qemu' not in rest and not any(a.startswith('--qemu=') for a in rest):
        rest += ['--qemu', str(capcom.DEFAULT_QEMU)]
    args = cycle.parse_args(rest)
    args.capcom_sync = own.capcom_sync
    result = run(args)
    raise SystemExit(0 if result.get('menu_cycle_state_passed') else 1)
