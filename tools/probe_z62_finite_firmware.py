"""Original-firmware r8 run with native device clocks, no host completion IRQs."""
import argparse
from pathlib import Path
from types import SimpleNamespace

import probe_z62_liveview as probe
import run_z62_raw_stream as parent
import run_z62_finite_stats as host
from z62_finite_stats_status import finite_stats_status


def run(output, duration, wall_limit):
    host.verify_build(host.DEFAULT_QEMU.resolve())
    original_config, original_observe = parent.configure_command, probe.observe_capture
    def configure(command, *a, **kw):
        return host.configure_command(original_config(command, *a, **kw), True)
    def observe(machine):
        return {**original_observe(machine), **finite_stats_status(machine)}
    parent.configure_command, probe.observe_capture = configure, observe
    args = SimpleNamespace(output=output, qemu=host.DEFAULT_QEMU,
        native_raw_stream=True, input_drain=True, frame_start=True, guest_errors=False,
        raw_boundary_experiment=False, raw_boundary_line=136, raw_transactions=0,
        metadata_after_raw=False, trace_lcd=False, duration=duration,
        wall_limit=wall_limit, poll=2)
    try:
        return probe.run(args)
    finally:
        parent.configure_command, probe.observe_capture = original_config, original_observe


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--duration', type=float, default=22)
    parser.add_argument('--wall-limit', type=float, default=600)
    args = parser.parse_args()
    if not 15 <= args.duration <= 60 or not 60 <= args.wall_limit <= 1800:
        parser.error('duration 15..60, wall-limit 60..1800 required')
    result = run(args.output, args.duration, args.wall_limit)
    last = result['samples'][-1].get('capture', {}).get('finite_stats_status')
    print('observation_completed=',result['observation_completed'], 'finite=',last)
    raise SystemExit(0 if result['observation_completed'] else 1)
