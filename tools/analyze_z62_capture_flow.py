"""Summarize a completed original capture-flow trace without claiming a photo."""
import argparse
import hashlib
import json
from pathlib import Path

from run_z62_capture_contacts import DEFAULT_QEMU, verify_build


def analyze(folder):
    path = folder / 'trace.json'
    raw = path.read_bytes()
    d = json.loads(raw)
    session = json.loads((folder / 'session.json').read_text(encoding='utf-8'))
    build = verify_build(DEFAULT_QEMU)
    if (d.get('failure') or d.get('cleanup_error') or d.get('process_closed') is not True or
            d.get('detach') != 'OK' or d.get('stop_reason') != 'virtual limit' or
            d.get('shutter_route_observation_completed') is not True or
            d.get('guest_state_patched') is not False or d.get('camera_accessed') is not False or
            d['observations'][-1]['virtual_seconds'] < d['virtual_limit'] or
            session['qemu_sha256'] != build['binary_sha256']):
        raise ValueError('Capture trace incomplete, modified or incompatible')
    requests, stages, retirements = [], [], []
    for h in d['hits']:
        label, e = h['label'], h.get('extra_observation', {})
        row = {'virtual_seconds': h['state']['virtual_seconds'], 'pc': h['registers']['pc'],
               'caller': h['registers']['lr']}
        if label == 'capture-main-request':
            requests.append({**row, 'r0': h['registers']['r0'], 'r1': h['registers']['r1'],
                             'request_48': e['request_48']})
        elif label in ('capture-flow-zero-step', 'capture-flow-normal-step'):
            data = bytes.fromhex(e['main_context_160'])
            stages.append({**row, 'flow': e['flow'], 'previous_stage': e['stage'],
                           'previous_callback': e['callback'], 'previous_result': e['callback_result'],
                           'outstanding': hex(int.from_bytes(data[20:24], 'little')),
                           'elapsed': int.from_bytes(data[24:28], 'little'),
                           'deadline': int.from_bytes(data[28:32], 'little')})
        elif label == 'capture-request-retire':
            retirements.append({**row, 'r0': h['registers']['r0'], 'r1': h['registers']['r1'],
                                'context_160': e['main_context_160']})
    transitions, previous = [], None
    for obs in d['observations']:
        w = obs['extra_words']['0xc23e2948']
        key = tuple(w[i] for i in (0, 1, 2, 3, 4, 5, 7))
        if key != previous:
            transitions.append({'virtual_seconds': obs['virtual_seconds'], 'active': w[0], 'flow': w[1],
                                'stage': w[2], 'callback': w[3], 'callback_result_word': w[4],
                                'outstanding': w[5], 'elapsed': w[6], 'deadline': w[7]})
            previous = key
    if not requests or not stages or not retirements:
        raise ValueError('Request, stage or retirement evidence missing')
    return {'schema': 1, 'trace_sha256': hashlib.sha256(raw).hexdigest(),
            'qemu_sha256': build['binary_sha256'], 'requests': requests, 'stages': stages,
            'retirements': retirements, 'context_transitions': transitions,
            'card_snapshot': d['virtual_card']['snapshot'],
            'raw_descriptor_hits': sum(h['label'] == 'raw-buffer-descriptor' for h in d['hits']),
            'sensor_frame_completions': d['observations'][-1]['capture']['sensors']['master']['frame-completions'],
            'breakpoints_perturb_timing': True, 'photo_capture_verified': False,
            'complete_emulator': False, 'flash_safety_verified': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = analyze(args.folder)
    with args.output.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2)
    print(json.dumps(result, indent=2))
