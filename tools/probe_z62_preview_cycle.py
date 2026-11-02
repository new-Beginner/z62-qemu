"""Strict original menu-cycle acceptance with the r9 preview device enabled."""
import argparse
import json
import probe_z62_finite_cycle as parent
import run_z62_preview as host
from z62_preview_status import preview_status


def run(args):
    if args.output.exists(): raise FileExistsError('Existing cycle evidence is protected')
    manifest=host.verify_build(args.qemu.resolve())
    original_config=parent.host.configure_command
    timing=parent.parent.previous.cycle.timing
    original_observe=timing.observe_capture
    original_stage=timing.stage
    owned=False
    def configure(command,*a,**kw): return host.configure_command(original_config(command,*a,**kw),True)
    def observe(machine): return {**original_observe(machine),**preview_status(machine)}
    def stage(*a,**kw):
        nonlocal owned
        work,record=original_stage(*a,**kw)
        owned=True
        record.update(preview_device=manifest,preview_enabled=True)
        return work,record
    parent.host.configure_command=configure;timing.observe_capture=observe;timing.stage=stage
    try:
        return parent.run(args)
    finally:
        parent.host.configure_command=original_config;timing.observe_capture=original_observe;timing.stage=original_stage
        for name in ('report.json','session.json'):
            path=args.output/name
            if owned and path.is_file():
                record=json.loads(path.read_text(encoding='utf-8'))
                record.update(preview_device=manifest,preview_enabled=True)
                path.write_text(json.dumps(record,indent=2),encoding='utf-8')


if __name__=='__main__':
    p=argparse.ArgumentParser(add_help=False)
    own,rest=p.parse_known_args()
    if '--qemu' not in rest and not any(a.startswith('--qemu=') for a in rest): rest+=['--qemu',str(host.DEFAULT_QEMU)]
    args=parent.parent.previous.cycle.parse_args(rest)
    args.raw_stream=args.input_drain=args.paired_sync=args.capcom_sync=True
    if not args.functional_raw or not args.raw_completion: p.error('functional-raw and raw-completion required')
    result=run(args)
    print('menu_cycle_state_passed=',result.get('menu_cycle_state_passed'))
    raise SystemExit(0 if result.get('menu_cycle_state_passed') else 1)
