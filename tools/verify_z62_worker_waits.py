"""Verify local call timing and original frame-event wait evidence for r16."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path

from run_z62_capture_contacts import DEFAULT_QEMU, verify_build

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'analysis/z62-capture-r16'


def verify():
    build = verify_build(DEFAULT_QEMU)
    results = {}
    for name, minimum in (('operation-waits2', 18), ('prepare-waits', 3)):
        folder = BASE / name
        raw = (folder / 'trace.json').read_bytes()
        d = json.loads(raw)
        s = json.loads((folder / 'session.json').read_text(encoding='utf-8'))
        if (d.get('failure') or d.get('cleanup_error') or d.get('process_closed') is not True or
                d.get('detach') != 'OK' or d.get('stop_reason') != 'virtual limit' or
                d.get('capture_setup_observed') is not True or d.get('live_anchors_verified') is not True or
                d.get('guest_state_patched') is not False or d.get('camera_accessed') is not False or
                d.get('shutter_contacts') or d['observations'][-1]['virtual_seconds'] < minimum or
                s['qemu_sha256'] != build['binary_sha256']):
            raise ValueError('Incomplete original worker observation: ' + name)
        pending, pairs = {}, []
        for hit in d['hits']:
            label, regs = hit['label'], hit['registers']
            if not label.startswith('worker-'):
                continue
            suffix = '-call' if label.endswith('-call') else '-return'
            key = (label[:-len(suffix)], hit['thread'], regs['sp'])
            if suffix == '-call':
                if key in pending:
                    raise ValueError('Ambiguous nested local call')
                pending[key] = hit
            elif key in pending:
                start = pending.pop(key)
                pairs.append({'name': key[0], 'start': start['state']['virtual_seconds'],
                              'seconds': round(hit['state']['virtual_seconds'] - start['state']['virtual_seconds'], 6),
                              'arguments': [start['registers'][f'r{i}'] for i in range(4)],
                              'return': regs['r0']})
        groups = defaultdict(list)
        for pair in pairs:
            groups[pair['name']].append(pair['seconds'])
        slow = [p for p in pairs if p['name'] == 'worker-prepare-frame' and p['seconds'] >= .29]
        if len(slow) < 5:
            raise ValueError('Repeated slow prepare-frame calls not established')
        if name == 'prepare-waits':
            timed_out = [p for p in pairs if p['name'] == 'worker-frame-event15' and
                         p['arguments'] == ['0xc1887cdc', '0x5', '0x0', '0x64'] and
                         p['return'] == '0x0' and .09 <= p['seconds'] <= .12]
            immediate = [p for p in pairs if p['name'] == 'worker-frame-event8' and
                         p['return'] == '0x1' and p['seconds'] <= .005]
            if len(timed_out) < 5 or len(immediate) < 5:
                raise ValueError('Frame-event outcomes not established')
        results[name] = {'trace_sha256': hashlib.sha256(raw).hexdigest(),
                         'end_virtual_seconds': d['observations'][-1]['virtual_seconds'],
                         'slow_prepare_calls': len(slow),
                         'timings': {k: {'pairs': len(v), 'minimum': min(v), 'maximum': max(v)}
                                     for k, v in groups.items()},
                         'pairs': pairs, 'unreturned_local_calls': len(pending)}
    return {'schema': 1, 'qemu_sha256': build['binary_sha256'], 'observations': results,
            'original_frame_event5_timeout_verified': True,
            'hardware_cause_of_event_timeout_verified': False,
            'photo_capture_verified': False, 'complete_emulator': False, 'flash_safety_verified': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = verify()
    with args.output.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2)
    print(json.dumps({k: v for k, v in result.items() if k != 'observations'}, indent=2))
    for name, record in result['observations'].items():
        print(name, record['timings'])
