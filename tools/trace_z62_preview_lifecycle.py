"""One menu/exit cycle followed by a long APPLV dwell, with sparse stop probes."""
import argparse
from pathlib import Path
from types import SimpleNamespace
import trace_z62_capture_setup as capture
import run_z62_raw_stream as raw
import run_z62_finite_stats as finite
import run_z62_preview as host
from z62_preview_status import preview_status

POINTS={0x10239734:'raw-buffer-descriptor',0x1036C14E:'raw-stop-flush-program',
        0x103B7680:'image-task-request',0x103C03BE:'backend-node-config'}
STATE={0x20380000:5,0x20380020:2,0x20380048:1,0x203800F0:1,
       0x20380300:8,0x20100000:9,0x20102000:7,0x20102100:7,0x20102600:9,
       0xC18095D0:32,0xC1809540:32,0xC1D52A84:8}


def run(output,exit_pin=0,duration=45,extra_hit_hook=None):
    host.verify_build(host.DEFAULT_QEMU.resolve())
    old=capture.POINTS,capture.STATE,raw.configure_command,capture.trace.observe_capture
    def configure(command,*a,**kw):
        return host.configure_command(finite.configure_command(old[2](command,*a,**kw)),True)
    def observe(machine): return {**old[3](machine),**preview_status(machine)}
    capture.POINTS=POINTS;capture.STATE={**old[1],**STATE}
    raw.configure_command=configure;capture.trace.observe_capture=observe
    args=SimpleNamespace(output=output,qemu=host.DEFAULT_QEMU,native_source=True,
        input_drain=True,frame_start=True,boundary_experiment=False,boundary_line=136,
        ready_bit_experiment=False,ready_set_experiment=False,lifecycle=False,frame_objects=False,
        ownership=False,metadata_event_experiment=False,startup_waits=False,
        virtual_limit=duration,wall_limit=900,menu_at=20,reopen_delay=1000,exit_pin=exit_pin,poll=2,max_stops=300)
    try: return capture.run(args,extra_hit_hook=extra_hit_hook)
    finally: capture.POINTS,capture.STATE,raw.configure_command,capture.trace.observe_capture=old


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--exit-pin',type=int,choices=(0,9),default=0)
    p.add_argument('--duration',type=float,default=45)
    args=p.parse_args()
    if not 35<=args.duration<=60: p.error('duration must be 35..60')
    result=run(args.output,args.exit_pin,args.duration)
    print(result['summary']['counts'])
    raise SystemExit(0 if result['capture_setup_observed'] else 1)
