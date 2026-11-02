"""Check raw and queued original encoder messages plus bounded ISO evidence."""
import argparse
import hashlib
import json
from pathlib import Path

import z62_encoder_input as physical
import z62_encoder_queue as queue
import z62_encoder_labels as labels
from export_z62_body_contract import original
from run_z62_capture_contacts import DEFAULT_QEMU, verify_build

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'analysis/z62-encoders-r20'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical(value):
    return json.loads(json.dumps(value))


def verify():
    build = verify_build(DEFAULT_QEMU)
    hashes = {}

    def load(name):
        data = (BASE/name).read_bytes()
        hashes[name] = hashlib.sha256(data).hexdigest()
        return json.loads(data)

    master, master_sha = original('master')
    names = []
    start = 0x10938B70 - 0x10020000
    for index in range(4):
        names.append(master[start+33*index:start+33*(index+1)].split(b'\0',1)[0].decode('ascii'))
    require(names == ['ID_ROTSW0_COMMAND_DIAL_MAIN','ID_ROTSW1_COMMAND_DIAL_SUB',
                      'ID_ROTSW2_COMMAND_DIAL_MAIN_VPOS','ID_ROTSW3_COMMAND_DIAL_SUB_VPOS'],
            'Original rotary-name table changed')
    ports = load('ports-with-controller.json')
    require(ports['completed'] and not ports['firmware_executed'] and
            ports['qemu_sha256'] == build['binary_sha256'] and
            {row['address'] for row in ports['ports'].values()} == set(range(0x40020000,0x40022000,0x400)),
            'GPIO topology evidence incomplete')

    def trace(name, duration):
        record = load(name+'/trace.json')
        session = load(name+'/session.json')
        require(record.get('process_closed') and record.get('detach') == 'OK' and
                record.get('stop_reason') == 'virtual limit' and not record.get('failure') and
                not record.get('cleanup_error') and record['observations'][-1]['virtual_seconds'] >= duration and
                session['qemu_sha256'] == build['binary_sha256'] and
                record['camera_accessed'] is False and record['guest_state_patched'] is False,
                'Incomplete original trace: '+name)
        messages = []
        for hit in record['hits']:
            if hit['label'] != 'encoder-message':
                continue
            require(hit['registers']['pc'] == '0x10436600', 'Unexpected input decoder')
            extra = hit['extra_observation']
            payload = bytes.fromhex(extra['encoder_payload'])
            require(len(payload) == 124 and payload[:4] == b'\1\0\0\0', 'Wrong original message layout')
            counts = [int.from_bytes(payload[offset:offset+1], 'little', signed=True) for offset in (11,12)]
            require(counts == extra['encoder_counts'], 'Reported counters differ from original payload')
            messages.append((counts,payload[0x16]))
        return record, messages

    for name, queued in (('messages',False),('queued-messages2',True),('cancel-messages',True)):
        record, messages = trace(name,10)
        receipt = load(name+'/encoder.json')
        require(receipt['completed'] and receipt['encoder_adapter'] == canonical(physical.identity()),
                'Physical encoder source identity changed')
        cancelled = name == 'cancel-messages'
        expected_counts = [[-1,0],[0,1]] if cancelled else [[1,0],[-1,0],[0,1],[0,-1]]
        require([value for value, _ in messages if value != [0,0]] == expected_counts,
                'Missing, duplicated or crossed original encoder counts')
        if cancelled:
            require(receipt['cancel_after_first_phase'] and len(receipt['events']) == 4 and
                    all(event['cancel_after_first_phase'] for event in receipt['events']),
                    'Cancellation was not exercised in all four directions')
        require(record['virtual_card']['before_sha256'] == record['virtual_card']['after_sha256'],
                'Snapshot card source changed')
        if queued:
            require(receipt['queued'] and receipt['queue_adapter'] == queue.identity(), 'Queue source changed')
    record, messages = trace('iso-combo',49)
    combo = load('iso-combo/combo.json')
    require(combo['completed'] and combo['automatic_shutter_events'] == [] and
            combo['guest_software_patched'] is False and combo['original_ready_at'] >= 30 and
            combo['virtual_card']['before_sha256'] == combo['virtual_card']['after_sha256'],
            'ISO combination observation incomplete')
    require([(value, iso) for value, iso in messages if value != [0,0]] == [([-1,0],1),([0,1],1)],
            'Original ISO modifier was not held with the encoder counts')
    review = load('visual-review.json')
    for filename, row in review['frames'].items():
        require(hashlib.sha256((BASE/filename).read_bytes()).hexdigest() == row['sha256'],
                'Reviewed original LCD image changed')
    for name, candidate in (('console-entry-final',False),('candidate-console-entry-final',True)):
        entry = load(name+'/report.json')
        receipt = load(name+'/encoder-check.json')
        require(entry['completed'] and entry['process_closed'] and entry['exit_code'] == 0 and
                not entry.get('forced_cleanup') and not entry.get('failure') and
                entry['candidate'] is candidate and receipt['completed'] and receipt['entry_completed'] and
                receipt['encoder_adapter'] == queue.identity() and receipt['encoder_labels'] == labels.identity() and
                receipt['invalid_input_rejected'], 'Final console entry failed: '+name)
        require([r['status']['issued_phases'] for r in receipt['rotations']] == [4,8,12,16],
                'HTTP movement did not produce four phases per request')
        if candidate:
            require(entry['status']['firmware_health_known'] is False, 'Candidate health must remain unknown')
    browser = load('browser-status.json')['state']
    require(browser['encoder_adapter'] == queue.identity() and browser['encoder_labels'] == labels.identity() and
            browser['encoder_input']['issued_phases'] == 16 and browser['encoder_input']['queued_phases'] == 0,
            'Browser click delivery incomplete')
    return {'schema':1, 'qemu_sha256':build['binary_sha256'], 'original_master_sha256':master_sha,
            'evidence_sha256':hashes, 'raw_counter_directions_verified':4,
            'queued_counter_directions_verified':4, 'baseline_and_candidate_http_verified':True,
            'original_cancel_first_phase_cases_verified':4,
            'browser_click_delivery_verified':True, 'iso_modifier_with_original_counts_verified':True,
            'original_iso_auto_disabled_and_lo03_visible':True,
            'main_iso_numeric_change_isolated_verified':False,
            'clockwise_direction_verified':False, 'shutter_aperture_verified':False,
            'complete_emulator':False, 'flash_safety_verified':False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path)
    args = parser.parse_args()
    result = verify()
    if args.output:
        with args.output.open('x',encoding='utf-8') as handle:
            json.dump(result,handle,indent=2)
    print(json.dumps({key:value for key,value in result.items() if key != 'evidence_sha256'},indent=2))
