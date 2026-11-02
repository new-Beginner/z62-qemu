"""Observe all eight external mode voltages and original UI without shutters."""
import argparse
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import probe_z62_no_lens as baseline
import run_z62_analog_input as hardware
import z62_mode_selector as selector
import z62_encoder_input as encoder


def run(output,card,group23,*,requested_codes=None,duration=89,rotation_step=1):
    build=hardware.verify_build()
    original_apply=baseline.route.shutter.apply_console
    events=[]
    frames=[]
    codes=list(selector.SAMPLES) if requested_codes is None else list(requested_codes)
    if not codes or len(codes)!=len(set(codes)) or any(type(code) is not int or code not in selector.SAMPLES for code in codes):
        raise ValueError('Select unique original mode codes')
    if type(duration) not in (int,float) or not 32+6*len(codes)+(7 if 3 in codes else 0) <= duration <= 120:
        raise ValueError('Observation duration does not cover the selected mode sequence')
    if type(rotation_step) is not int or rotation_step not in (-1,1):
        raise ValueError('Select one positive or negative main-dial detent')
    index=0
    pending_frame=False
    next_time=None
    rotation_cursor=None
    def apply(source):
        original_apply(source)
        selector.apply_console(source)
        encoder.apply_console(source)
    def hit(remote,registers):
        if registers['pc']!=0x10436600:
            return {}
        payload=remote.read(registers['r0'],124)
        return {'selector_payload':payload.hex(),'original_mode_code':payload[15],
                'encoder_counts':[int.from_bytes(payload[offset:offset+1],'little',signed=True) for offset in (11,12)]}
    def observe(machine,row):
        nonlocal index,pending_frame,next_time,rotation_cursor
        now=row['virtual_seconds']
        if next_time is None:
            with machine.io:
                ready=machine._words(0xC1821EB8,1)[0]
                joined=machine._words(0xC1868AE8,1)[0]
            if now<30 or row['index']!=3 or ready!=0 or joined!=3:
                return None
            next_time=now
        if index==len(codes) or now<next_time:
            return None
        code=codes[index]
        if rotation_cursor is not None and rotation_cursor<4:
            phase=encoder.ENCODERS[0]['positive' if rotation_step>0 else 'negative'][rotation_cursor]
            with machine.io:
                encoder.drive_phase(machine,0,phase)
            event={'virtual_seconds':now,'kind':'external-main-encoder','phase':phase,'mode_code':code,'step':rotation_step}
            events.append(event)
            print('MODE_ENCODER',json.dumps(event),flush=True)
            rotation_cursor+=1
            next_time=now+(5.5 if rotation_cursor==4 else .2)
            return event
        if not pending_frame:
            with machine.io:
                event=selector.drive(machine,code)
            event.update(virtual_seconds=now,kind='external-mode-voltage')
            events.append(event)
            pending_frame=True
            next_time=now+5.5
            print('MODE_VOLTAGE',json.dumps(event),flush=True)
            return event
        data=machine.frame_png()
        filename=f'mode-code-{code}' + ('-main-step.png' if rotation_cursor==4 else '.png')
        with (output/filename).open('xb') as handle:
            handle.write(data)
        frame={'file':filename,'code':code,'virtual_seconds':now,
               'sha256':hashlib.sha256(data).hexdigest(),'foreground_index':row['index'],
               'status_codes':row['status_codes']}
        frames.append(frame)
        print('MODE_FRAME',json.dumps(frame),flush=True)
        if code==3 and rotation_cursor is None:
            rotation_cursor=0
            next_time=now+.3
            return None
        rotation_cursor=None
        index+=1
        pending_frame=False
        next_time=now+.3
        return None
    # This is a selector/UI experiment, not an ISP acceptance run. Retain
    # original input breakpoints, readiness, firmware status and screenshots,
    # but omit unrelated per-frame capture-device diagnostic queries.
    with patch.object(baseline.host,'DEFAULT_QEMU',hardware.DEFAULT_QEMU), \
         patch.object(baseline.route.capture.trace,'observe_capture',lambda machine: {}), \
         patch.object(baseline.route,'preview_status',lambda machine: {}), \
         patch.object(baseline.route.shutter,'apply_console',apply):
        record,fixture=baseline.run(output,card,group23,True,False,duration,
            extra_points={0x10436600:'mode-selector-input'},extra_hit_hook=hit,
            extra_observation_hook=observe,max_stops=300,automatic_shutter=False,wall_limit=3000,
            observation_timeout_recovery=True)
    receipt={'schema':1,'hardware_sha256':build['binary_sha256'],'selector':selector.identity(),
             'events':events,'frames':frames,'encoder_adapter':encoder.identity(),
             'requested_codes':codes,'requested_virtual_seconds':duration,'main_rotation_step':rotation_step,
             'completed':bool(fixture['observation_completed'] and index==len(codes) and
                              record.get('process_closed') and not record.get('failure') and
                              record.get('shutter_contacts')==[]),
             'observation_profile':'original-selector-messages-and-LCD',
             'mode_names_verified':False,'full_mode_functions_verified':False,
             'all_modes_preview_continuity_verified':False,'shutter_change_verified':False}
    with (output/'selector.json').open('x',encoding='utf-8') as handle:
        json.dump(receipt,handle,indent=2)
    print(receipt)
    return receipt


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--card',type=Path,required=True)
    parser.add_argument('--group23',type=Path,required=True)
    parser.add_argument('--codes',type=int,nargs='+')
    parser.add_argument('--duration',type=float,default=89)
    parser.add_argument('--dial-step',type=int,choices=(-1,1),default=1)
    args=parser.parse_args()
    raise SystemExit(0 if run(args.output,args.card,args.group23,requested_codes=args.codes,duration=args.duration,rotation_step=args.dial_step)['completed'] else 1)
