"""Correlate physical mode codes with original scalar store values, read-only."""
import argparse
import json
from pathlib import Path
from unittest.mock import patch

import probe_z62_no_lens as baseline
import run_z62_analog_input as hardware
import z62_mode_selector as selector
import z62_parameter_observation as parameters


def run(output,card,group23):
    build=hardware.verify_build()
    descriptor_identity=parameters.identity()
    original_apply=baseline.route.shutter.apply_console
    codes=[3,2,1,0,6,5,4,10]
    cursor=0
    next_time=2.0
    events=[]
    def apply(source):
        original_apply(source)
        selector.apply_console(source)
    def hit(remote,registers):
        if registers['pc']!=0x10436600:
            return {}
        raw=remote.read(registers['r0'],124)
        return {'input_payload':raw.hex(),'wire_mode':raw[15],
                'parameters_before_decode':parameters.observe_remote(remote)}
    def observe(machine,row):
        nonlocal cursor,next_time
        with machine.io:
            row['parameters']=parameters.observe_machine(machine)
        if cursor==len(codes) or row['virtual_seconds']<next_time:
            return None
        with machine.io:
            event=selector.drive(machine,codes[cursor])
        event['virtual_seconds']=row['virtual_seconds']
        events.append(event)
        cursor+=1
        next_time=row['virtual_seconds']+.7
        print('MODE_STORE',json.dumps(event),flush=True)
        return event
    with patch.object(baseline.host,'DEFAULT_QEMU',hardware.DEFAULT_QEMU), \
         patch.object(baseline.route.capture.trace,'observe_capture',lambda machine:{}), \
         patch.object(baseline.route,'preview_status',lambda machine:{}), \
         patch.object(baseline.route.shutter,'apply_console',apply):
        record,fixture=baseline.run(output,card,group23,True,False,10,
            extra_points={0x10436600:'mode-store-input'},extra_hit_hook=hit,
            extra_observation_hook=observe,max_stops=100,automatic_shutter=False,
            observation_timeout_recovery=True)
    receipt={'schema':1,'qemu_sha256':build['binary_sha256'],'descriptor_identity':descriptor_identity,
             'events':events,'completed':bool(fixture['observation_completed'] and cursor==len(codes)),
             'mode_names_verified':False,'guest_functions_called':False,'guest_memory_written':False}
    with (output/'parameters.json').open('x',encoding='utf-8') as handle:
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
