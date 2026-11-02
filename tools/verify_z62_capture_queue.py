"""Verify original capture enqueue rejection and queue contents on frozen r13."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from run_z62_capture_contacts import DEFAULT_QEMU, verify_build

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / 'analysis/z62-capture-r16/capture-queue'


def verify(native_boundary=False):
    if native_boundary:
        import run_z62_raw_boundary as host
        folder = ROOT / 'analysis/z62-capture-r17/capture-queue-native'
        expected_counts = {'0x10322449': 59, '0x10323c2b': 1}
        build = host.verify_build(host.DEFAULT_QEMU)
    else:
        folder = FOLDER
        expected_counts = {'0x10322449': 59, '0x1031fd2b': 1}
        build = verify_build(DEFAULT_QEMU)
    raw = (folder / 'trace.json').read_bytes()
    d = json.loads(raw)
    session = json.loads((folder / 'session.json').read_text(encoding='utf-8'))
    if (d.get('process_closed') is not True or d.get('detach') != 'OK' or
            d.get('failure') or d.get('cleanup_error') or d.get('stop_reason') != 'virtual limit' or
            d.get('shutter_route_observation_completed') is not True or
            d.get('guest_state_patched') is not False or d.get('camera_accessed') is not False or
            d.get('live_anchors_verified') is not True or d.get('breakpoint_window_active') is not False or
            d['observations'][-1]['virtual_seconds'] < 36 or
            session['qemu_sha256'] != build['binary_sha256']):
        raise ValueError('Incomplete or incompatible capture queue observation')
    rejects = [h for h in d['hits'] if h['label'] == 'capture-enqueue-return']
    wrapper = [h for h in d['hits'] if h['label'] == 'capture-submit-return']
    if len(rejects) != 1 or len(wrapper) != 1:
        raise ValueError('Expected one bounded submission and its return')
    h = rejects[0]
    r, q = h['registers'], h['extra_observation']
    tasks = q['work_ids_in_order']
    if (r['pc'] != '0x1031627e' or r['r0'] != '0x0' or r['r4'] != '0x10320019' or
            r['r7'] != '0x103eae81' or wrapper[0]['registers']['r0'] != '0x0' or
            q['count'] != 60 or q['capacity'] != 60 or len(tasks) != 60 or
            Counter(tasks) != expected_counts or
            any(x['label'] == 'capture-queued-worker' for x in d['hits'])):
        raise ValueError('The claimed rejected work or queue contents differ')
    events = d['breakpoint_window_events']
    if [e['kind'] for e in events] != ['open', 'close'] or events[0]['thread'] != events[1]['thread']:
        raise ValueError('Submission call frame window did not close normally')
    return {'schema': 1, 'native_boundary': native_boundary, 'trace_sha256': hashlib.sha256(raw).hexdigest(),
            'qemu_sha256': build['binary_sha256'], 'capture_enqueue_rejected': True,
            'virtual_seconds': h['state']['virtual_seconds'], 'queue_capacity': 60,
            'queue_count': 60, 'work_id_counts': dict(Counter(tasks)),
            'capture_worker_observed': False, 'slow_worker_root_cause_verified': False,
            'photo_capture_verified': False, 'complete_emulator': False, 'flash_safety_verified': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--native', action='store_true')
    args = parser.parse_args()
    result = verify(args.native)
    if args.output:
        with args.output.open('x', encoding='utf-8') as handle:
            json.dump(result, handle, indent=2)
    print(json.dumps(result, indent=2))
