"""Read native image-register submissions and ISR callback tables on verified r8."""
import argparse
from pathlib import Path

import probe_z62_liveview as live
import probe_z62_finite_firmware as finite

REGIONS={
    'image_irq_registers':(0x20100000,9),
    'image_transfer_channels':(0x20100400,256),
    'image_unit_submissions':(0x20100800,432),
    'image_command_banks':(0x20102000,128),
    'image_address_lists':(0x20102200,128),
    'image_sequence_banks':(0x20102600,40),
    'image_routes':(0x20102880,42),
    'raw_processor_registers':(0x20380000,256),
    'image_callback_state':(0xC1801D60,16),
    'image_irq_decode_table':(0xC1801E38,30),
    'raw_irq_callback_state':(0xC1801ECC,8),
    'statistics_channel2':(0x2006A650,8),
    'statistics_channel3':(0x2006A750,8),
    'statistics_channel4':(0x2006A850,8),
}


def run(output,duration,wall_limit):
    original=dict(live.REGISTERS)
    live.REGISTERS.update(REGIONS)
    try:
        return finite.run(output,duration,wall_limit)
    finally:
        live.REGISTERS.clear();live.REGISTERS.update(original)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--duration',type=float,default=22)
    p.add_argument('--wall-limit',type=float,default=600)
    args=p.parse_args()
    if not 17<=args.duration<=45 or not 60<=args.wall_limit<=1800:
        p.error('duration 17..45, wall-limit 60..1800 required')
    result=run(args.output,args.duration,args.wall_limit)
    print('observation_completed=',result['observation_completed'])
    raise SystemExit(0 if result['observation_completed'] else 1)
