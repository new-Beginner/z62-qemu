"""Native r9 preview run without host pixels, boundary IRQs or software patches."""
import argparse
from pathlib import Path
from types import SimpleNamespace
import probe_z62_liveview as probe
import run_z62_raw_stream as raw
import run_z62_finite_stats as finite
import run_z62_preview as host
from z62_finite_stats_status import finite_stats_status
from z62_preview_status import preview_status


def run(output,duration,wall_limit,*,sd_card=None):
    host.verify_build(host.DEFAULT_QEMU.resolve())
    original_config,original_observe=raw.configure_command,probe.observe_capture
    def configure(command,*a,**kw):
        return host.configure_command(finite.configure_command(original_config(command,*a,**kw)),True)
    def observe(machine):
        return {**original_observe(machine),**finite_stats_status(machine),**preview_status(machine)}
    raw.configure_command,probe.observe_capture=configure,observe
    args=SimpleNamespace(output=output,qemu=host.DEFAULT_QEMU,native_raw_stream=True,
        input_drain=True,frame_start=True,guest_errors=False,raw_boundary_experiment=False,
        raw_boundary_line=136,raw_transactions=0,metadata_after_raw=False,trace_lcd=False,
        duration=duration,wall_limit=wall_limit,poll=2,sd_card=sd_card)
    try: return probe.run(args)
    finally: raw.configure_command,probe.observe_capture=original_config,original_observe


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--duration',type=float,default=22)
    p.add_argument('--wall-limit',type=float,default=900)
    args=p.parse_args()
    if not 17<=args.duration<=60 or not 60<=args.wall_limit<=1800: p.error('Invalid duration/wall-limit')
    result=run(args.output,args.duration,args.wall_limit)
    print('observation_completed=',result['observation_completed'])
    print(result['samples'][-1].get('capture',{}).get('preview_status'))
    raise SystemExit(0 if result['observation_completed'] else 1)
