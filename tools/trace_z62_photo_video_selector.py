"""Observe sustained expander pin0 as a selector, without assuming its name.

The old EXIT label is not a hardware contract. Capture the original byte 0x57,
LCD and restoration path before calling this the photo/video lever.
"""
import argparse
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import probe_z62_no_lens as baseline
import run_z62_analog_input as hardware


def run(output,card,group23):
    build=hardware.verify_build()
    events=[]
    frames=[]
    phase=0
    deadline=None
    plan=(('frame','before'),('level',0),('frame','pin0-low'),('level',1),('frame','pin0-high'))
    def hit(remote,registers):
        if registers['pc']!=0x10436600:
            return {}
        data=remote.read(registers['r0'],124)
        return {'input_payload':data.hex(),'selector_byte_57':data[0x57]}
    def observe(machine,row):
        nonlocal phase,deadline
        now=row['virtual_seconds']
        if deadline is None:
            with machine.io:
                ready=machine._words(0xC1821EB8,1)[0]
                joined=machine._words(0xC1868AE8,1)[0]
            if now<30 or row['index']!=3 or ready!=0 or joined!=3:
                return None
            deadline=now
        if phase==len(plan) or now<deadline:
            return None
        action,value=plan[phase]
        if action=='frame':
            data=machine.frame_png()
            name=str(value)+'.png'
            with (output/name).open('xb') as handle:
                handle.write(data)
            frames.append({'file':name,'sha256':hashlib.sha256(data).hexdigest(),
                           'virtual_seconds':now,'index':row['index'],'status_codes':row['status_codes']})
            deadline=now+.5
        else:
            with machine.io:
                args={'path':'/machine/peripheral/keys','property':'input-levels'}
                before=machine.qmp.command('qom-get',args)
                if type(before) is not int or not 0<=before<=0xffffff:
                    raise ValueError('Expander physical levels unavailable')
                after=(before&~1)|value
                machine.qmp.command('qom-set',{**args,'value':after})
                if machine.qmp.command('qom-get',args)!=after:
                    raise ValueError('Persistent selector readback mismatch')
            event={'kind':'persistent-selector-pin0','level':value,'virtual_seconds':now,
                   'before_levels':before,'after_levels':after}
            events.append(event)
            print('SELECTOR_PIN0',json.dumps(event),flush=True)
            deadline=now+8
        phase+=1
        return events[-1] if action=='level' else None
    with patch.object(baseline.host,'DEFAULT_QEMU',hardware.DEFAULT_QEMU), \
         patch.object(baseline.route.capture.trace,'observe_capture',lambda machine:{}), \
         patch.object(baseline.route,'preview_status',lambda machine:{}):
        record,fixture=baseline.run(output,card,group23,True,False,55,
            extra_points={0x10436600:'persistent-selector-input'},extra_hit_hook=hit,
            extra_observation_hook=observe,max_stops=200,automatic_shutter=False,
            wall_limit=2200,observation_timeout_recovery=True)
    result={'schema':1,'qemu_sha256':build['binary_sha256'],'events':events,'frames':frames,
            'completed':bool(fixture['observation_completed'] and phase==len(plan) and
                             record.get('process_closed') and not record.get('failure')),
            'physical_photo_video_identity_verified':False,'video_recording_verified':False}
    with (output/'selector.json').open('x',encoding='utf-8') as handle:
        json.dump(result,handle,indent=2)
    print(result)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--card',type=Path,required=True)
    parser.add_argument('--group23',type=Path,required=True)
    args=parser.parse_args()
    raise SystemExit(0 if run(args.output,args.card,args.group23)['completed'] else 1)
