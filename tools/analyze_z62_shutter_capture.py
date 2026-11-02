"""Summarize a completed shutter probe and independently inspect its virtual SD."""
import argparse
import hashlib
import json
from pathlib import Path
from inspect_z62_virtual_card import inspect
from z62_virtual_sd import digest


def analyze(folder):
    raw = (folder/'report.json').read_bytes()
    record = json.loads(raw)
    if not record.get('observation_completed') or not record.get('clean_exit'):
        raise ValueError('Require a completed, normally closed probe')
    probe = record['shutter_capture_experiment']
    media = probe['virtual_media']
    card = Path(media['path'])
    if digest(card) != media['final_sha256']:
        raise ValueError('Preserved virtual media changed since shutdown')
    inventory = inspect(card)
    samples = record['samples']
    phases = []
    previous = None
    switches = set()
    for sample in samples:
        state = sample.get('capture', {}).get('shutter_capture_probe')
        if state is None:
            continue
        switches.add(int(state['switch_words'][0], 16))
        if state['phase'] == previous:
            continue
        previous = state['phase']
        phases.append({'phase': previous, 'time': sample['virtual_seconds'],
                       'switch_words': state['switch_words'],
                       'command_banks': state['image_command_banks']})
    images = [f for f in inventory['files'] if f.get('format_hint') in ('JPEG', 'TIFF/NEF')]
    events = probe['events']
    full = next((e for e in events if e['gpio_g_pin'] == 13 and e['level'] == 0 and e['driven']), None)
    return {'schema': 1, 'report_sha256': hashlib.sha256(raw).hexdigest(),
            'camera_accessed': False, 'guest_software_patched': record.get('guest_software_patched'),
            'process_closed': record.get('clean_exit'), 'input_events': events,
            'half_press_observed': any(w & 0x80000000 for w in switches),
            'full_press_observed': any(w & 0x40000000 for w in switches),
            'switch_words_observed': [hex(w) for w in sorted(switches)],
            'phases': phases, 'final_virtual_seconds': samples[-1]['virtual_seconds'],
            'seconds_after_full_press': samples[-1]['virtual_seconds']-full['virtual_seconds'] if full else None,
            'preview_final': samples[-1]['capture']['preview_status'],
            'capture_register_samples': [{'time': r['virtual_seconds'],
                'mode': r['registers']['capture_mode']['words'],
                'state': r['registers']['capture_state']['words']} for r in record['register_samples']],
            'virtual_media': media, 'inventory': inventory,
            'encoded_image_candidates': len(images), 'photo_saved_verified': False,
            'complete_emulator': False, 'flash_safety_verified': False}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('folder', type=Path)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    result = analyze(args.folder)
    with args.output.open('x', encoding='utf-8') as out:
        json.dump(result, out, indent=2)
    print(json.dumps({k: result[k] for k in ('half_press_observed', 'full_press_observed',
        'final_virtual_seconds', 'seconds_after_full_press', 'encoded_image_candidates',
        'photo_saved_verified')}))
    print(json.dumps(result['inventory'], indent=2))
