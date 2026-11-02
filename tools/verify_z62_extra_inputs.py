"""Verify r21 analogue device and bounded extra-key/joystick input evidence."""
import argparse
import hashlib
import json
from pathlib import Path

import run_z62_analog_input as hardware
import z62_extra_inputs as inputs
import z62_extra_console as console

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'analysis/z62-body-r21'


def require(condition,message):
    if not condition:
        raise ValueError(message)


def canonical(value):
    return json.loads(json.dumps(value))


def verify():
    build=hardware.verify_build()
    hashes={}
    def load(name):
        raw=(BASE/name).read_bytes()
        hashes[name]=hashlib.sha256(raw).hexdigest()
        return json.loads(raw)
    native=load('adc-native.json')
    required=('all_channels_mutable','legacy_inputs_preserved','invalid_values_atomic','inflight_latch_verified',
              'next_conversion_uses_new_level','all_banks_resolutions_alignments','eoc_ack_preserved',
              'reset_preserves_external_level','disable_cancels_pending_conversion','disabled_completion_not_forged')
    require(native['completed'] and native['binary_sha256']==build['binary_sha256'] and
            native['firmware_executed'] is False and native['conversion_cases']==24 and
            all(native.get(name) is True for name in required),'Native ADC contract incomplete')
    negative=load('adc-parent-negative.json')
    require(not negative['completed'] and 'input-channel0' in negative['failure']['message'] and
            'not found' in negative['failure']['message'],'Old-kernel negative control changed')
    record=load('extra-inputs/trace.json')
    session=load('extra-inputs/session.json')
    receipt=load('extra-inputs/inputs.json')
    require(record['process_closed'] and record['detach']=='OK' and record['stop_reason']=='virtual limit' and
            not record.get('failure') and not record.get('cleanup_error') and
            record['guest_state_patched'] is False and record['camera_accessed'] is False and
            record['observations'][-1]['virtual_seconds']>=13 and receipt['completed'] and
            receipt['input_adapter']==canonical(inputs.identity()),'Original extra-input observation incomplete')
    sequence=[]
    latest=None
    for hit in record['hits']:
        if hit['label']!='extra-body-input':
            continue
        require(hit['registers']['pc']=='0x10436600','Unexpected original input decoder')
        detail=hit['extra_observation']
        payload=bytes.fromhex(detail['body_payload'])
        gpio={str(key):payload[config['wire_offset']] for key,config in inputs.GPIO_KEYS.items()}
        joystick={name:payload[offset] for name,offset in inputs.JOY_WIRE.items()}
        require(gpio==detail['gpio_flags'] and joystick==detail['joystick_flags'],
                'Decoded fields differ from actual original payload')
        require(all(value in (0,1) for value in [*gpio.values(),*joystick.values()]),'Unexpected input byte')
        active=['gpio-'+key for key,value in gpio.items() if value]+['joy-'+key for key,value in joystick.items() if value]
        require(len(active)<=1,'Unintended simultaneous button or joystick action')
        if active:
            sequence.append(active[0])
        latest=active
    expected=['gpio-'+str(key) for key in inputs.GPIO_KEYS]+['joy-'+name for name in inputs.JOY_WIRE]
    require(sequence==expected and latest==[],'Missing, duplicated or stuck original input action')
    for folder,candidate in (('extra-http2',False),('extra-http-candidate',True)):
        base=load(folder+'/report.json')
        check=load(folder+'/extra-check.json')
        require(base['completed'] and base['process_closed'] and base['exit_code']==0 and
                not base.get('forced_cleanup') and not base.get('failure') and
                base['candidate'] is candidate and check['completed'] and check['release_all_verified'] and
                check['invalid_input_rejected'] and check['adapter']==canonical(console.identity()),
                'Extra console input or identity failed: '+folder)
        require([row['key'] for row in check['gpio']]==list(inputs.GPIO_KEYS) and
                [row['position'] for row in check['joystick']]==list(inputs.JOY_WIRE),'Incomplete HTTP cases')
        for row in check['joystick']:
            require(row['pressed_levels']==inputs.joystick_levels(0xffffff,row['position']) and
                    row['released_levels']==0xffffff,'Joystick physical readback differs')
        if candidate:
            require(base['status']['firmware_health_known'] is False,'Candidate health must remain unknown')
    return {'schema':1,'analog_qemu_sha256':build['binary_sha256'],
            'gpio_observation_qemu_sha256':session['qemu_sha256'],'evidence_sha256':hashes,
            'runtime_adc_native_verified':True,'original_gpio_keys_verified':4,
            'original_joystick_positions_verified':9,'baseline_candidate_http_verified':True,
            'mode_selection_verified':False,'photo_video_lever_verified':False,
            'autofocus_recording_verified':False,'complete_emulator':False,'flash_safety_verified':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    result=verify()
    if args.output:
        with args.output.open('x',encoding='utf-8') as handle:
            json.dump(result,handle,indent=2)
    print(json.dumps({key:value for key,value in result.items() if key!='evidence_sha256'},indent=2))
