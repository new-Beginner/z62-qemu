"""Verify r19 original input evidence, independent of complete-camera claims."""
import argparse
import hashlib
import json
from pathlib import Path

import export_z62_body_contract as contract
import z62_body_controls as body
from run_z62_capture_contacts import DEFAULT_QEMU, verify_build

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'analysis/z62-body-controls-r19'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify():
    build = verify_build(DEFAULT_QEMU)
    hashes = {}

    def load(name):
        raw = (BASE / name).read_bytes()
        hashes[name] = hashlib.sha256(raw).hexdigest()
        return json.loads(raw)

    static = load('static-contract.json')
    require(static == contract.recover(), 'Original static contract or its source evidence changed')
    # The initial 0803D8C8 export starts two instructions into the function.
    # The corrected entry proves summary base and the slot-5 source for pin1.
    corrected = ROOT / 'analysis/z62-ghidra/controller-summary-entry-r19'
    metadata = json.loads((corrected / 'manifest.json').read_text(encoding='utf-8'))
    require(metadata['completed'] and metadata['original_unchanged'] and
            metadata['functions'] == ['0x803d8c4'] and
            metadata['input_sha256'] == static['firmware_sha256']['controller'] and
            metadata['export_audit']['all_exports_structurally_usable'],
            'Corrected controller summary entry is missing')
    for filename in ('manifest.json', '803d8c4.c', '803d8c4.asm'):
        hashes['controller-summary-entry-r19/' + filename] = hashlib.sha256(
            (corrected / filename).read_bytes()).hexdigest()
    for name, candidate in (('body-http', False), ('body-http-candidate', True)):
        report = load(name + '/report.json')
        require(report.get('completed') and report.get('process_closed') and report.get('exit_code') == 0
                and not report.get('failure') and not report.get('forced_cleanup')
                and not report.get('cleanup_error'), 'Incomplete console observation: ' + name)
        require(report['body_controls'] == body.identity() and report['qemu_sha256'] == build['binary_sha256']
                and report['candidate'] is candidate and report['camera_accessed'] is False,
                'Console identity mismatch: ' + name)
        expected = {key: pin for key, label, pin, code, shortcut, group in body.CONTROLS}
        require(len(report['controls']) == len(expected), 'Missing electrical input results')
        for row in report['controls']:
            pin = expected.pop(row['id'])
            require(row['pin'] == pin and row['pressed_levels'] == (0xffffff ^ (1 << pin))
                    and row['released_levels'] == 0xffffff, 'Unintended or missing physical input')
        require(not expected and report['release_all_verified'], 'Input release incomplete')
        if candidate:
            require(report['initial_status']['firmware_health_known'] is False
                    and report['final_status']['firmware_health_known'] is False,
                    'Candidate must retain unknown health')
        for key, filename in (('html', 'index.html'), ('javascript', 'console.js')):
            require(hashlib.sha256((BASE / name / filename).read_bytes()).hexdigest()
                    == report['assets_sha256'][key], 'Captured console asset changed')
    report = load('pin8/report.json')
    session = load('pin8/session.json')
    require(report.get('observation_completed') and report.get('clean_exit') and
            not report.get('failure') and not report.get('cleanup_error') and
            session['qemu_sha256'] == build['binary_sha256'] and
            report['camera_accessed'] is False and report['guest_software_patched'] is False,
            'Incomplete original playback observation')
    events = report['body_input_probe']['events']
    require([(row['pin'], row['level']) for row in events] == [(8,0),(8,1),(24,0),(24,1)],
            'Unexpected input sequence')
    samples = report['samples']
    require(any(int(row.get('capture', {}).get('body_input_probe', {}).get('switch_words', ['0','0'])[1], 16) & 2
                for row in samples), 'Original PLAY switch bit never observed')
    require(any(row.get('index') == 2 and events[0]['virtual_seconds'] < row.get('virtual_seconds', 0)
                < events[2]['virtual_seconds'] for row in samples), 'Original APPPLAY not reached')
    tail = []
    for row in reversed(samples):
        if row.get('index') != 3 or (row.get('virtual_seconds') or 0) <= events[3]['virtual_seconds']:
            break
        tail.append(row)
    tail.reverse()
    require(len(tail) > 1 and tail[-1]['virtual_seconds'] - tail[0]['virtual_seconds'] >= 5,
            'Less than five guest seconds of returned shooting view')
    counts = [row['capture']['preview_status']['engines']['master']['preview-batches'] for row in tail]
    require(counts[-1] > counts[0] and all(row.get('firmware_status_codes') == [] for row in tail),
            'Preview stopped or original status codes returned')
    review = load('visual-review.json')
    for filename, evidence in review['observations'].items():
        require(hashlib.sha256((BASE / filename).read_bytes()).hexdigest() == evidence['sha256'],
                'Reviewed original LCD frame changed')
    return {'schema': 1, 'qemu_sha256': build['binary_sha256'], 'body_controls': body.identity(),
            'evidence_sha256': hashes, 'static_routes': len(static['routes']),
            'baseline_electrical_inputs_verified': 9, 'candidate_electrical_inputs_verified': 9,
            'playback_no_card_and_half_return_verified': True,
            'returned_preview_batches': [counts[0], counts[-1]],
            'all_new_button_functions_verified': False, 'photo_playback_verified': False,
            'complete_emulator': False, 'flash_safety_verified': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = verify()
    if args.output:
        with args.output.open('x', encoding='utf-8') as handle:
            json.dump(result, handle, indent=2)
    print(json.dumps({key: value for key, value in result.items()
                      if key not in ('evidence_sha256', 'body_controls')}, indent=2))
