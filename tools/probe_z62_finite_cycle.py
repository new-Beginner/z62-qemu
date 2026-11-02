"""Strict menu-cycle test on r8, preserving the existing acceptance conditions."""
import argparse
import probe_z62_raw_stream_cycle as parent
import run_z62_finite_stats as host
from z62_finite_stats_status import finite_stats_status


def run(args):
    host.verify_build(args.qemu.resolve())
    original_config = parent.host.configure_command
    original_observe = parent.previous.cycle.timing.observe_capture
    def configure(command,*a,**kw):
        return host.configure_command(original_config(command,*a,**kw),True)
    def observe(machine):
        return {**original_observe(machine),**finite_stats_status(machine)}
    parent.host.configure_command = configure
    parent.previous.cycle.timing.observe_capture = observe
    try:
        return parent.run(args)
    finally:
        parent.host.configure_command = original_config
        parent.previous.cycle.timing.observe_capture = original_observe


if __name__ == '__main__':
    p=argparse.ArgumentParser(add_help=False)
    own,rest=p.parse_known_args()
    if '--qemu' not in rest and not any(a.startswith('--qemu=') for a in rest):
        rest += ['--qemu',str(host.DEFAULT_QEMU)]
    args=parent.previous.cycle.parse_args(rest)
    args.raw_stream=args.input_drain=args.paired_sync=args.capcom_sync=True
    if not args.functional_raw or not args.raw_completion:
        p.error('functional-raw and raw-completion are required')
    result=run(args)
    print('menu_cycle_state_passed=',result.get('menu_cycle_state_passed'))
    raise SystemExit(0 if result.get('menu_cycle_state_passed') else 1)
