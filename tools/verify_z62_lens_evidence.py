"""Verify the lens restart cycle and original CPU writes, without photo claims."""
import argparse
import hashlib
import json
from pathlib import Path

from run_z62_capture_contacts import DEFAULT_QEMU, verify_build

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'analysis/z62-capture-r15'


def verify():
    build = verify_build(DEFAULT_QEMU)
    records, hashes = {}, {}
    for name in ('lens-control', 'lens-policy', 'lens-presence', 'lens-presence-code',
                 'lens-error-reconnect', 'lens-error7-writer', 'slot7-watch', 'lens-detect', 'hold5'):
        path = BASE / name / 'trace.json'
        d = json.loads(path.read_text(encoding='utf-8'))
        session = json.loads((path.parent / 'session.json').read_text(encoding='utf-8'))
        if (d.get('process_closed') is not True or d.get('detach') != 'OK' or
                d.get('failure') or d.get('cleanup_error') or
                d.get('stop_reason') != 'virtual limit' or
                d['observations'][-1]['virtual_seconds'] < d['virtual_limit'] or
                session['qemu_sha256'] != build['binary_sha256'] or
                d.get('guest_state_patched') is not False or d.get('camera_accessed') is not False or
                d['virtual_card']['before_sha256'] != d['virtual_card']['after_sha256']):
            raise ValueError('Incomplete or incompatible evidence: ' + name)
        records[name] = d
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    replies = [h for h in records['lens-control']['hits'] if h['label'] == 'system-lens-result'
               and h['registers']['r0'] in ('0x4100006', '0x4100007', '0x4100009')]
    if len(replies) < 6 or any(h['extra_observation']['reply_32'][:8] != '00000000' for h in replies):
        raise ValueError('Unexpected upper-level lens reply words')
    policy = [h['extra_observation']['policy_event'] for h in records['lens-policy']['hits']
              if h['label'] == 'system-lens-policy-event']
    if not any(policy[i:i+2] == ['0x2f', '0x2e'] for i in range(len(policy)-1)):
        raise ValueError('Stop/start policy pair missing')
    checks = [h for h in records['lens-error-reconnect']['hits']
              if h['label'] == 'lens-error-reconnect-check' and h['registers']['lr'] == '0x102f1357']
    if len(checks) < 3 or any(h['state']['extra_words']['0xc293d28c'][7] != '0x1' for h in checks):
        raise ValueError('Slot7 is not present at the reconnect decisions')
    original = (ROOT / 'artifacts/z62-reference-1.70/master.bin').read_bytes()
    writes = [h for h in records['slot7-watch']['hits'] if h['label'] == 'native-ram-write'
              and h.get('watch_before') == '00000000' and h.get('watch_after') == '01000000']
    if len(writes) < 3:
        raise ValueError('Insufficient observed original writes')
    for h in writes:
        if (h['watch_address'] != '0xc293d2a8' or h['registers']['pc'] != '0x10345330' or
                h['registers']['lr'] != '0x1030a8a9' or h['registers']['r0'] != '0x7' or
                h['registers']['r1'] != '0x1' or
                bytes.fromhex(h['watch_instruction_4']) != original[0x325330:0x325334]):
            raise ValueError('Slot7 producer differs from the verified original store')
    if any(h['label'] == 'lens-error7-store' for h in records['lens-error7-writer']['hits']):
        raise ValueError('600C candidate was also reached; update the interpretation')
    held = records['hold5']
    if held.get('shutter_route_observation_completed') is not True:
        raise ValueError('Long contact observation incomplete')
    events = held['shutter_contacts']
    press = next(e for e in events if (e['pin'], e['level']) == (13, 0))
    release = next(e for e in events if (e['pin'], e['level']) == (13, 1))
    actual_hold = release['virtual_seconds'] - press['virtual_seconds']
    # The schedule uses nominal absolute deadlines; observation polling shifts
    # each delivered edge. Prove extension over the old .5s recipe and report
    # the measured interval, rather than claiming an exact five-second hold.
    if held.get('full_press_hold_seconds') != 5 or actual_hold <= .5 or any(
            h['label'] in ('capture-enter-state3', 'capture-permission-ready-worker') for h in held['hits']):
        raise ValueError('Long hold behavior needs new interpretation')
    return {'schema': 1, 'qemu_sha256': build['binary_sha256'], 'evidence_sha256': hashes,
            'upper_reply_zero_is_not_error_free_lens': True,
            'slot7_original_writer': '0x10345330', 'slot7_caller': '0x1030A8A9',
            'slot7_set_count': len(writes), 'candidate_600c_branch_reached': False,
            'nominal_full_hold_seconds': 5, 'actual_full_hold_seconds': round(actual_hold, 6),
            'capture_permission_restored': False, 'complete_emulator': False,
            'photo_capture_verified': False, 'flash_safety_verified': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = verify()
    if args.output:
        with args.output.open('x', encoding='utf-8') as handle:
            json.dump(result, handle, indent=2)
    print(json.dumps(result, indent=2))
