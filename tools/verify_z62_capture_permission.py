"""Verify the C1.70 state/requirement diagnosis without claiming photo success."""
import argparse
import hashlib
import json
from pathlib import Path

from run_z62_capture_contacts import DEFAULT_QEMU, verify_build

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'analysis/z62-capture-r14'


def blockers(snapshot):
    words = [int(value, 16) for value in snapshot['extra_words']['0xc23e3f24']]
    if len(words) < 16:
        raise ValueError('Missing native requirement maps')
    return [i for i in range(124) if words[i // 32] & words[4 + i // 32] & (1 << (i % 32))]


def verify():
    manifest = verify_build(DEFAULT_QEMU)
    hashes, records = {}, {}
    for name in ('full-state-targeted', 'permission', 'requirements-boot', 'components',
                 'component-types', 'group23-header', 'group23-capture'):
        path = EVIDENCE / name / 'trace.json'
        d = json.loads(path.read_text(encoding='utf-8'))
        session_path = path.parent / 'session.json'
        session = json.loads(session_path.read_text(encoding='utf-8'))
        if (d.get('process_closed') is not True or d.get('detach') != 'OK' or
                d.get('failure') or d.get('cleanup_error') or d.get('stop_reason') != 'virtual limit' or
                d['observations'][-1]['virtual_seconds'] < d['virtual_limit'] or
                session['qemu_sha256'] != manifest['binary_sha256'] or
                d.get('guest_state_patched') is not False or d.get('camera_accessed') is not False or
                d['virtual_card']['before_sha256'] != d['virtual_card']['after_sha256']):
            raise ValueError('Incomplete or incompatible observation: ' + name)
        hashes[name + '/trace.json'] = hashlib.sha256(path.read_bytes()).hexdigest()
        hashes[name + '/session.json'] = hashlib.sha256(session_path.read_bytes()).hexdigest()
        records[name] = d
    for name in ('full-state-targeted', 'permission', 'group23-capture'):
        if records[name].get('shutter_route_observation_completed') is not True:
            raise ValueError('Full contact observation incomplete: ' + name)
    def full_decision(name):
        hits = [h for h in records[name]['hits'] if h['label'] == 'capture-next-state-return'
                and h['state']['virtual_seconds'] > records[name]['readiness_receipt']['virtual_seconds']
                and h['registers']['r0'] == '0x1']
        if len(hits) != 1:
            raise ValueError('Ambiguous full request decision: ' + name)
        return hits[0]
    before = full_decision('permission')
    after = full_decision('group23-capture')
    if blockers(before['state']) != [0x25, 0x2C] or blockers(after['state']) != [0x25]:
        raise ValueError('Unexpected release blockers at the actual decisions')
    stores = [h for h in records['full-state-targeted']['hits'] if h['label'] == 'capture-state-byte-store']
    if len(stores) != 1 or stores[0]['registers']['r0'] != '0x1':
        raise ValueError('Native byte state assignment missing')
    if any(h['label'] == 'capture-enter-state3' for h in records['group23-capture']['hits']):
        raise ValueError('New capture behavior needs review instead of this diagnosis')
    def notices(name):
        return {(int(h['registers']['r0'], 16), int(h['registers']['r1'], 16))
                for h in records[name]['hits'] if h['label'] == 'capture-component-notice'}
    if (0x04400046, 0x47) in notices('components') or (0x04400046, 0x50) not in notices('components'):
        raise ValueError('Unexpected component baseline')
    for name in ('group23-header', 'group23-capture'):
        if not {(0x04400046, 0x47), (0x04400046, 0x50)} <= notices(name):
            raise ValueError('Original component readiness not observed')
        receipt_path = EVIDENCE / name / 'fixture.json'
        receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
        image_path = Path(receipt['path'])
        data = image_path.read_bytes()
        if (receipt.get('enabled') is not True or receipt.get('factory_calibration') is not False or
                not receipt.get('observation_completed') or len(data) != 0xE0000 or
                data[-4:] != b'ENDM' or any(data[:-4]) or
                hashlib.sha256(data).hexdigest() != receipt['sha256']):
            raise ValueError('Experimental storage receipt/image mismatch')
        hashes[name + '/fixture.json'] = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    return {'schema': 1, 'qemu_sha256': manifest['binary_sha256'], 'evidence_sha256': hashes,
            'native_full_request_observed': True, 'native_capture_state_byte': '0xC23E3F76',
            'baseline_blockers': ['0x25', '0x2c'], 'group23_blockers': ['0x25'],
            'group23_component_ready_observed': True, 'factory_calibration_recovered': False,
            'capture_state3_reached': False, 'photo_capture_verified': False,
            'complete_emulator': False, 'flash_safety_verified': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = verify()
    if args.output:
        with args.output.open('x', encoding='utf-8') as handle:
            json.dump(result, handle, indent=2)
    print(json.dumps(result, indent=2))
