"""Verify the original input-event0 route; optionally require native r17 delivery."""
import argparse
import hashlib
import json
from pathlib import Path

import run_z62_capture_contacts as parent
import run_z62_raw_boundary as native

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'analysis/z62-capture-r17'


def pairs(data, name):
    pending, result = {}, []
    for h in data['hits']:
        key = (h['thread'], h['registers']['sp'])
        if h['label'] == name + '-call':
            pending[key] = h
        elif h['label'] == name + '-return' and key in pending:
            a = pending.pop(key)
            result.append({'start': a['state']['virtual_seconds'],
                           'seconds': round(h['state']['virtual_seconds']-a['state']['virtual_seconds'], 6),
                           'result': int(h['registers']['r0'], 16)})
    return result


def verify(include_native):
    names = ['frame-delivery-baseline', 'frame-delivery-pulse']
    if include_native:
        names.append('frame-delivery-native')
    records, summaries = {}, {}
    for name in names:
        folder = BASE / name
        raw = (folder / 'trace.json').read_bytes()
        d = json.loads(raw)
        s = json.loads((folder / 'session.json').read_text(encoding='utf-8'))
        summary = json.loads((folder / 'delivery-summary.json').read_text(encoding='utf-8'))
        expected = (native if name.endswith('native') else parent)
        build = expected.verify_build(expected.DEFAULT_QEMU)
        if (d.get('process_closed') is not True or d.get('detach') != 'OK' or d.get('failure') or
                d.get('cleanup_error') or d.get('stop_reason') != 'virtual limit' or
                d.get('guest_state_patched') is not False or d.get('camera_accessed') is not False or
                d.get('capture_setup_observed') is not True or d.get('live_anchors_verified') is not True or
                d['observations'][-1]['virtual_seconds'] < 3 or d.get('shutter_contacts') or
                summary.get('observation_completed') is not True or s['qemu_sha256'] != build['binary_sha256']):
            raise ValueError('Incomplete or incompatible delivery evidence: ' + name)
        events = [h for h in d['hits'] if h['label'] == 'frame-source-callback' and h['registers']['r0'] == '0x41a000f']
        waits = pairs(d, 'event5')
        records[name] = d
        summaries[name] = {'trace_sha256': hashlib.sha256(raw).hexdigest(),
                           'binary_sha256': build['binary_sha256'], 'original_041a000f_count': len(events),
                           'event5_waits': waits, 'frame_processing_waits': pairs(d, 'frame-process-b')}
        if name.endswith('baseline'):
            if events or d.get('device_experiments') or sum(w['result'] == 0 for w in waits) < 4:
                raise ValueError('Baseline does not show the expected missing boundary')
        elif name.endswith('pulse'):
            pulses = [e for e in d.get('device_experiments', []) if e.get('kind') == 'single-input-event0-route-test']
            if len(pulses) != 1 or len(events) != 1 or pulses[0]['native_raw_batches'] < 1:
                raise ValueError('Expected one RAW-backed external route experiment')
            start = pulses[0]['virtual_seconds']
            after = [w for w in waits if w['start'] > start]
            irqs = [h for h in d['hits'] if h['label'] == 'input-bank0-callback']
            if (len(irqs) != 1 or not irqs[0]['extra_observation']['input_irq_payload_32'].startswith('01000000') or
                    not start <= events[0]['state']['virtual_seconds'] < start+.05 or not after or
                    after[0]['result'] != 1 or after[0]['seconds'] > .01):
                raise ValueError('Original IRQ/message/wait causal chain not demonstrated')
        else:
            after = [w for w in waits if w['start'] >= 1]
            if (d.get('device_experiments') or summary['pulses'] or len(events) < 20 or
                    summary.get('native_boundary_identity') != native.device.identity() or
                    len(after) < 4 or any(w['result'] != 1 or w['seconds'] > .04 for w in after)):
                raise ValueError('Native boundary did not restore repeated original event waits')
    return {'schema': 1, 'evidence': summaries, 'original_input_event0_route_verified': True,
            'native_boundary_verified': include_native, 'remaining_processing_wait_resolved': False,
            'photo_capture_verified': False, 'complete_emulator': False, 'flash_safety_verified': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.native)
    with args.output.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2)
    print(json.dumps(result, indent=2))
