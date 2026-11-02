"""Verify actual GPIO and sub-selector signals through original MCU messages."""
import argparse
import json
from pathlib import Path
from unittest.mock import patch

import probe_z62_no_lens as baseline
import z62_extra_inputs as inputs


def run(output,card,group23):
    original_apply=baseline.route.shutter.apply_console
    plan=[]
    for key in inputs.GPIO_KEYS:
        plan.extend([('gpio',key,0),('gpio',key,1)])
    for position in inputs.JOY_WIRE:
        plan.extend([('joystick',position),('joystick','neutral')])
    cursor=0
    next_time=2.0
    events=[]
    def apply(source):
        original_apply(source)
        inputs.apply_console(source)
    def observe(machine,row):
        nonlocal cursor,next_time
        now=row['virtual_seconds']
        if cursor==len(plan) or now<next_time:
            return None
        op=plan[cursor]
        with machine.io:
            if op[0]=='gpio':
                inputs.drive_gpio(machine,op[1],op[2])
                extra={'gpio_levels':dict(machine._body_gpio_levels)}
            else:
                extra=inputs.drive_joystick(machine,op[1])
        event={'virtual_seconds':now,'operation':op,**extra}
        events.append(event)
        cursor+=1
        next_time=now+.25
        print('BODY_EXTRA',json.dumps(event),flush=True)
        return event
    def hit(remote,registers):
        if registers['pc']!=0x10436600:
            return {}
        payload=remote.read(registers['r0'],124)
        return {'body_payload':payload.hex(),
                'gpio_flags':{str(key):payload[value['wire_offset']] for key,value in inputs.GPIO_KEYS.items()},
                'joystick_flags':{name:payload[offset] for name,offset in inputs.JOY_WIRE.items()}}
    with patch.object(baseline.route.shutter,'apply_console',apply):
        record,fixture=baseline.run(output,card,group23,True,False,13,
            extra_points={0x10436600:'extra-body-input'},extra_hit_hook=hit,
            extra_observation_hook=observe,max_stops=150)
    receipt={'schema':1,'input_adapter':inputs.identity(),'events':events,
             'completed':bool(fixture['observation_completed'] and cursor==len(plan)
                              and record.get('process_closed') and not record.get('failure')),
             'photographic_functions_verified':False}
    with (output/'inputs.json').open('x',encoding='utf-8') as handle:
        json.dump(receipt,handle,indent=2)
    print(receipt)
    return receipt


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--card',type=Path,required=True)
    parser.add_argument('--group23',type=Path,required=True)
    args=parser.parse_args()
    raise SystemExit(0 if run(args.output,args.card,args.group23)['completed'] else 1)
