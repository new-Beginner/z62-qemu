"""Bounded original-mode, shutter-display and physical mode-console evidence."""
import argparse
import hashlib
import json
from pathlib import Path

import run_z62_analog_input as hardware
import z62_mode_selector as selector
import z62_mode_console as console
import z62_parameter_observation as parameters

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'analysis/z62-body-r21'


def require(condition,message):
    if not condition: raise ValueError(message)


def canonical(value): return json.loads(json.dumps(value))


def verify(baseline_console=None,candidate_console=None):
    build=hardware.verify_build()
    hashes={}
    def load(name):
        raw=(BASE/name).read_bytes()
        hashes[name]=hashlib.sha256(raw).hexdigest()
        return json.loads(raw)
    def trace(folder,duration):
        d=load(folder+'/trace.json')
        session=load(folder+'/session.json')
        require(d.get('process_closed') and d.get('detach')=='OK' and not d.get('failure') and
                not d.get('cleanup_error') and d.get('stop_reason')=='virtual limit' and
                d['observations'][-1]['virtual_seconds']>=duration and
                d['guest_state_patched'] is False and d['camera_accessed'] is False and
                d.get('shutter_contacts')==[] and session['qemu_sha256']==build['binary_sha256'],
                'Incomplete original observation: '+folder)
        for gap in d.get('observation_timeouts',[]):
            require(not gap['control_commands_replayed'] and gap['monitor']['replayed_commands']==0,
                    'Observation recovery replayed a control command')
        require(d['virtual_card']['before_sha256']==d['virtual_card']['after_sha256'],
                'Source virtual card changed')
        return d
    d=trace('mode-selector3',89)
    receipt=load('mode-selector3/selector.json')
    require(receipt['completed'] and receipt['selector']==canonical(selector.identity()),'Mode selector identity changed')
    changes=[row for row in receipt['events'] if row['kind']=='external-mode-voltage']
    require([row['code'] for row in changes]==list(selector.SAMPLES),'Eight positions missing')
    require(all(row['sample_after']==selector.SAMPLES[row['code']] for row in changes),'Wrong physical mode voltage')
    observed=[]
    for hit in d['hits']:
        if hit['label']!='mode-selector-input': continue
        require(hit['registers']['pc']=='0x10436600','Unexpected decoder')
        detail=hit['extra_observation']
        data=bytes.fromhex(detail['selector_payload'])
        require(len(data)==124 and data[15]==detail['original_mode_code'],'Mode did not come from original payload')
        if not observed or observed[-1]!=data[15]: observed.append(data[15])
    require(observed==list(selector.SAMPLES),'Original controller did not consume every position')
    review=load('mode-visual-review.json')
    require(review['eight_position_observation']['healthy_storage_baseline'] is False,
            'Do not silently reclassify the For observation as healthy storage')
    for name,row in review['eight_position_observation']['frames'].items():
        require(hashlib.sha256((BASE/'mode-selector3'/name).read_bytes()).hexdigest()==row['sha256'],
                'Reviewed mode frame changed')
    shutter=review['manual_shutter_observation']
    for folder,step,after in (('manual-shutter-4g',1,'positive_after_sha256'),
                              ('manual-shutter-slower',-1,'negative_after_sha256')):
        record=trace(folder,47)
        run=load(folder+'/selector.json')
        require(run['completed'] and run['requested_codes']==[3],'Manual-mode observation missing')
        counts=[]
        for hit in record['hits']:
            if hit['label']!='mode-selector-input': continue
            payload=bytes.fromhex(hit['extra_observation']['selector_payload'])
            pair=[int.from_bytes(payload[offset:offset+1],'little',signed=True) for offset in (11,12)]
            if pair!=[0,0]: counts.append(pair)
        require(counts==[[step,0]],'Unexpected main-dial count')
        require(hashlib.sha256((BASE/folder/'mode-code-3.png').read_bytes()).hexdigest()==shutter['before_sha256'] and
                hashlib.sha256((BASE/folder/'mode-code-3-main-step.png').read_bytes()).hexdigest()==shutter[after],
                'Reviewed shutter frame changed')
    d=trace('mode-store-codes',10)
    receipt=load('mode-store-codes/parameters.json')
    require(receipt['completed'] and receipt['descriptor_identity']==canonical(parameters.identity()) and
            not receipt['guest_functions_called'] and not receipt['guest_memory_written'],'Parameter observation is not read-only')
    mapping={0:0,1:1,2:2,3:3,4:7,5:8,6:9,10:4}
    for index,event in enumerate(receipt['events']):
        end=receipt['events'][index+1]['virtual_seconds'] if index+1<len(receipt['events']) else 10.1
        rows=[row for row in d['observations'] if event['virtual_seconds']+.05<row['virtual_seconds']<end]
        require(any(row['parameters']['0x0']['value']==mapping[event['code']] and
                    row['parameters']['0x1']['value']==mapping[event['code']] for row in rows),
                'Physical mode code was not reflected in the original parameter store')
    console_paths={}
    for folder,candidate in ((baseline_console or 'mode-console-http-final',False),
                             (candidate_console or 'mode-console-candidate-final',True)):
        folder=str(folder)
        console_paths['candidate' if candidate else 'baseline']=str((BASE/folder).resolve())
        entry=load(folder+'/report.json')
        mode=load(folder+'/mode-check.json')
        extra=load(folder+'/extra-check.json')
        encoders=load(folder+'/encoder-check.json')
        require(entry['completed'] and entry['process_closed'] and entry['exit_code']==0 and
                not entry.get('forced_cleanup') and not entry.get('failure') and
                entry['candidate'] is candidate and entry['status']['hardware_version']=='2026.10.30-r21' and
                mode['completed'] and extra['completed'] and encoders['completed'] and
                mode['adapter']==canonical(console.identity()) and mode['locked_write_rejected'] and
                mode['release_keeps_detent'] and mode['invalid_inputs_rejected'],'Console contract failed: '+folder)
        require([row['code'] for row in mode['positions']]==list(console.MODES.values()),'Missing HTTP dial positions')
        if candidate: require(entry['status']['firmware_health_known'] is False,'Candidate health must remain unknown')
    return {'schema':1,'qemu_sha256':build['binary_sha256'],'evidence_sha256':hashes,
            'console_evidence_paths':console_paths,
            'original_mode_codes_verified':8,'original_mode_store_values_verified':8,
            'manual_U1_U2_U3_auto_visible':True,'m_shutter_display_8000_to_6400_verified':True,
            'baseline_candidate_mode_lock_and_voltage_verified':True,
            'P_S_photographic_functions_verified':False,'aperture_verified':False,
            'photo_video_lever_verified':False,'complete_emulator':False,'flash_safety_verified':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--baseline-console',type=lambda value:Path(value).resolve())
    parser.add_argument('--candidate-console',type=lambda value:Path(value).resolve())
    args=parser.parse_args()
    result=verify(args.baseline_console,args.candidate_console)
    if args.output:
        with args.output.open('x',encoding='utf-8') as handle: json.dump(result,handle,indent=2)
    print(json.dumps({key:value for key,value in result.items() if key!='evidence_sha256'},indent=2))
