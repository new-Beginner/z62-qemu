# SPDX-License-Identifier: GPL-2.0-or-later
"""Strict original-firmware menu regression on the independently verified r7."""
import argparse
import json

import probe_z62_capcom_cycle as previous
import run_z62_raw_stream as host
from z62_raw_stream_status import raw_stream_status


def run(args):
    if args.output.exists():
        raise FileExistsError('Existing cycle evidence is protected')
    manifest = host.verify_build(args.qemu.resolve())
    original = (previous.capcom.configure_command, previous.cycle.timing.observe_capture,
                previous.cycle.timing.stage)
    owned = False
    def configure(command, enabled):
        return host.configure_command(original[0](command, enabled), args.raw_stream,
                                      drain=args.input_drain, paired=args.paired_sync)
    def observe(machine):
        value = original[1](machine)
        value.update(raw_stream_status(machine))
        return value
    def stage(*a, **kw):
        nonlocal owned
        owned = True
        work, record = original[2](*a, **kw)
        record.update(raw_stream_device=manifest, raw_stream=args.raw_stream,
                      input_drain_completion=args.input_drain, frame_start_phase=args.paired_sync)
        return work, record
    previous.capcom.configure_command = configure
    previous.cycle.timing.observe_capture = observe
    previous.cycle.timing.stage = stage
    try:
        return previous.run(args)
    finally:
        previous.capcom.configure_command, previous.cycle.timing.observe_capture, \
            previous.cycle.timing.stage = original
        if owned:
            for name in ('report.json', 'session.json'):
                path = args.output/name
                if path.is_file():
                    record = json.loads(path.read_text(encoding='utf-8'))
                    record.update(raw_stream_device=manifest, raw_stream=args.raw_stream,
                                  input_drain_completion=args.input_drain, frame_start_phase=args.paired_sync)
                    path.write_text(json.dumps(record, indent=2), encoding='utf-8')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__, add_help=False)
    p.add_argument('--raw-stream', action='store_true')
    p.add_argument('--input-drain', action='store_true')
    p.add_argument('--paired-sync', action='store_true')
    p.add_argument('--capcom-sync', action=argparse.BooleanOptionalAction, default=True)
    own, rest = p.parse_known_args()
    if '--qemu' not in rest and not any(a.startswith('--qemu=') for a in rest):
        rest += ['--qemu', str(host.DEFAULT_QEMU)]
    args = previous.cycle.parse_args(rest)
    for name in ('raw_stream', 'input_drain', 'paired_sync', 'capcom_sync'):
        setattr(args, name, getattr(own, name))
    if args.raw_stream and not args.functional_raw:
        p.error('--raw-stream requires --functional-raw')
    result = run(args)
    raise SystemExit(0 if result.get('menu_cycle_state_passed') else 1)
