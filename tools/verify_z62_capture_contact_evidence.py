"""Verify native GPIO delivery separately from complete photographic behavior."""
import argparse
import hashlib
import json
from pathlib import Path

from run_z62_capture_contacts import DEFAULT_QEMU, verify_build

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'analysis/z62-capture-r13'


def read(relative):
    path = EVIDENCE / relative
    return json.loads(path.read_text(encoding='utf-8')), hashlib.sha256(path.read_bytes()).hexdigest()


def completed_trace(record):
    return (record.get('shutter_route_observation_completed') is True and
            record.get('process_closed') is True and record.get('detach') == 'OK' and
            not record.get('failure') and not record.get('cleanup_error') and
            record.get('guest_state_patched') is False and record.get('camera_accessed') is False and
            record.get('stop_reason') == 'virtual limit' and
            record['observations'][-1]['virtual_seconds'] >= record['virtual_limit'] and
            record['virtual_card']['before_sha256'] == record['virtual_card']['after_sha256'])


def check():
    build = verify_build(DEFAULT_QEMU)
    native, nsha = read('native-r13.json')
    baseline, bsha = read('contact-route-off/trace.json')
    enabled, esha = read('contact-route-on/trace.json')
    sessions = [read(name + '/session.json') for name in ('contact-route-off', 'contact-route-on')]
    if any(s.get('qemu_sha256') != build['binary_sha256'] or s.get('guest_patched') is not False
           for s, _ in sessions):
        raise ValueError('Firmware sessions do not match the unpatched r13 kernel')
    if native.get('completed') is not True:
        raise ValueError('Native GPIO test did not complete')
    for record in (baseline, enabled):
        if not completed_trace(record):
            raise ValueError('A paired firmware observation is incomplete')
        if len(record.get('shutter_contacts', [])) != 4 or not record.get('readiness_receipt'):
            raise ValueError('Missing ready/contact receipts')
    def callbacks(record):
        since = record['shutter_contacts'][0]['virtual_seconds']
        return [h for h in record['hits'] if h['label'] == 'capture-contact-isr-callback'
                and h['state']['virtual_seconds'] >= since]
    if callbacks(baseline):
        raise ValueError('Disabled control unexpectedly delivered capture GPIO')
    actual = [(int(h['registers']['r0'], 16), int(h['registers']['r1'], 16)) for h in callbacks(enabled)]
    if actual != [(69, 1), (70, 1), (70, 0), (69, 0)]:
        raise ValueError('Original ISR did not consume the four expected contact transitions: ' + repr(actual))
    expected_workers = {'capture-contact-half-worker', 'capture-contact-full-worker',
                        'capture-contact-full-release-worker', 'capture-contact-half-release-worker'}
    since = enabled['shutter_contacts'][0]['virtual_seconds']
    reached = {h['label'] for h in enabled['hits'] if h['state']['virtual_seconds'] >= since}
    if not expected_workers <= reached:
        raise ValueError('Original capture worker delivery incomplete')
    last = enabled['shutter_contacts'][-1]['additional_contact_path']['diagnostics']
    if last != {'capture-contact-levels': 0, 'capture-contact-edges': 4, 'capture-contact-irq-events': 4}:
        raise ValueError('Unexpected final contact counters')
    return {'schema': 1, 'qemu_sha256': build['binary_sha256'],
            'evidence_sha256': {'native-r13.json': nsha, 'contact-route-off/trace.json': bsha,
                                'contact-route-on/trace.json': esha,
                                'contact-route-off/session.json': sessions[0][1],
                                'contact-route-on/session.json': sessions[1][1]},
            'original_gpio_and_workers_verified': True,
            'original_callback_sequence': actual,
            'complete_emulator': False, 'photo_capture_verified': False,
            'flash_safety_verified': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = check()
    if args.output:
        with args.output.open('x', encoding='utf-8') as handle:
            json.dump(result, handle, indent=2)
    print(json.dumps(result, indent=2))
