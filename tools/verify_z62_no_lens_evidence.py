"""Validate r16 external lens-contact, capture permission and console evidence.

This checks original observations and image identities, not photographic output
or camera flashing safety. Snapshot card hashes prove host-image preservation.
"""
import argparse
import hashlib
import json
from pathlib import Path

from run_z62_capture_contacts import DEFAULT_QEMU, verify_build
from z62_capture_input import identity as input_identity
from z62_lens_contact import identity as lens_identity

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'analysis/z62-capture-r16'
GROUP23 = 'c7dd14358b45b2813fdee85fc587bcdd5899f7a81e0d5830513d631235bcc700'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify():
    build = verify_build(DEFAULT_QEMU)
    hashes = {}
    def load(name):
        path = BASE / name
        raw = path.read_bytes()
        hashes[name] = hashlib.sha256(raw).hexdigest()
        return json.loads(raw)
    records = {}
    for name in ('controller-pin', 'controller-report', 'no-lens-short', 'no-lens-capture'):
        d = load(name + '/trace.json')
        session = load(name + '/session.json')
        require(d.get('process_closed') is True and d.get('detach') == 'OK' and
                not d.get('failure') and not d.get('cleanup_error') and
                d.get('stop_reason') == 'virtual limit' and
                d['observations'][-1]['virtual_seconds'] >= d['virtual_limit'] and
                d.get('guest_state_patched') is False and d.get('camera_accessed') is False and
                d['virtual_card']['snapshot'] is True and
                d['virtual_card']['before_sha256'] == d['virtual_card']['after_sha256'] and
                session['qemu_sha256'] == build['binary_sha256'], 'Incomplete trace: ' + name)
        records[name] = d
    def hits(name, label):
        return [h for h in records[name]['hits'] if h['label'] == label]
    baseline = hits('controller-pin', 'controller-lens-report-entry')
    absent = hits('no-lens-short', 'controller-lens-report-entry')
    require(len(baseline) == len(absent) == 1, 'Unexpected lens report count')
    for rows, present in ((baseline, 1), (absent, 0)):
        h = rows[0]
        e = h['extra_observation']
        require(int(h['registers']['r0'], 16) == present and
                e['lens_descriptor_16'] == '6000000052f900200018024001000000' and
                e['lens_gpio_port'] == '0x40021800' and e['lens_gpio_mask'] == '0x1' and
                (int.from_bytes(bytes.fromhex(e['lens_gpio_mode_pull_idr'])[-4:], 'little') & 1) == 1-present,
                'External PG0 does not explain original presence report')
    for name, present in (('controller-report', 1), ('no-lens-short', 0)):
        frame = hits(name, 'controller-lens-report-fields')
        require(len(frame) == 1 and bytes.fromhex(frame[0]['extra_observation']['controller_lens_frame_16'])[12] == present,
                'Controller frame presence mismatch')
    require(any(h['registers']['r0'] == '0x0' for h in hits('no-lens-short', 'lens-present-state-set')),
            'Master did not consume absent lens')
    for name in ('no-lens-short', 'no-lens-capture'):
        fixture = load(name + '/fixture.json')
        require(fixture['absent_lens'] is True and fixture['observation_completed'] is True and
                fixture['group23']['sha256'] == GROUP23 and fixture['group23']['factory_calibration'] is False,
                'Experimental fixture provenance missing')
    capture = records['no-lens-capture']
    require(capture.get('shutter_route_observation_completed') is True and
            len(capture['shutter_contacts']) == 4 and capture['virtual_limit'] == 60,
            'Full shutter observation incomplete')
    require(len(hits('no-lens-capture', 'capture-enter-state3')) == 1 and
            len(hits('no-lens-capture', 'capture-enter-state0')) == 1,
            'Natural capture state transition missing')
    require(all(int(r['extra_words']['0xc293d28c'][7], 16) == 0 and
                not ({0x25, 0x26, 0x35} & {int(c, 16) if isinstance(c, str) else c for c in r['status_codes']})
                for r in capture['observations']), 'Lens reconnect/status35 returned')
    require(len(hits('no-lens-capture', 'raw-buffer-descriptor')) == 2 and
            capture['observations'][-1]['capture']['sensors']['master']['frame-completions'] == 0,
            'Photo data behavior changed: review before changing conclusions')
    for name in ('console-entry3', 'candidate-console-entry', 'cmd-entry', 'candidate-cmd-entry'):
        d = load(name + '/report.json')
        s, after = d['status'], d['capture_input_after']
        require(d.get('completed') is True and d.get('process_closed') is True and d.get('exit_code') == 0 and
                not d.get('forced_cleanup') and not d.get('failure') and
                d.get('capture_input_http_verified') is True and d.get('monitor_transport_verified') is True and
                s['hardware_version'] == '2026.10.29-r13' and s['host_version'] == '2026.10.29-no-lens-r16' and
                s['input_adapter'] == input_identity() and s['lens_contact'] == lens_identity() and
                after['known'] is True and after['capture-contact-levels'] == 0 and
                after['capture-contact-edges'] == 4 and after['capture-contact-irq-events'] == 4 and
                after['body_input_levels'] == [1, 1], 'Console contract failed: ' + name)
        require(s['capture_acceptance'] == {'photo_saved_verified': False, 'complete_emulator': False},
                'Console overstates acceptance')
        if d['candidate']:
            require(s['firmware_health_known'] is False and s['firmware_status_codes'] is None,
                    'Candidate health must remain unknown')
        if 'cmd-entry' in name:
            require(d['entry'] == 'start-z6ii-qemu.cmd', 'Expected actual CMD evidence')
    menu = load('no-lens-menu/report.json')
    session = load('no-lens-menu/session.json')
    require(menu.get('process_closed') is True and menu.get('experiment_completed') is True and
            menu.get('menu_cycle_state_passed') is True and menu.get('isolated_half_press_verified') is True and
            menu.get('preview_after_half_press_verified') is True and menu['no_guest_state_writes'] is True and
            menu['camera_accessed'] is False and menu['input_adapter'] == input_identity() and
            session['qemu_sha256'] == build['binary_sha256'], 'Menu cycle incomplete')
    require(len(menu['dwells']) == 2 and all(d['passed'] and d['last']-d['first'] >= 5 and
            d['last_batches'] > d['first_batches'] for d in menu['dwells']), 'Continuous preview not shown')
    review = load('visual-review.json')
    require(review['menu_navigation_visible'] is True and review['preview_recovery_visible'] is True and
            review['photos_verified'] is False, 'Missing bounded visual review')
    for name, record in review['observations'].items():
        require(hashlib.sha256((BASE / name).read_bytes()).hexdigest() == record['sha256'],
                'Reviewed image changed: ' + name)
    return {'schema': 1, 'qemu_sha256': build['binary_sha256'], 'evidence_sha256': hashes,
            'external_pg0_no_lens_verified': True, 'capture_permission_restored': True,
            'capture_state3_verified': True, 'menu_preview_cycles_verified': 2,
            'http_two_stage_contacts_verified': True, 'experimental_factory_calibration': False,
            'photo_capture_verified': False, 'complete_emulator': False, 'flash_safety_verified': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = verify()
    if args.output:
        with args.output.open('x', encoding='utf-8') as handle:
            json.dump(result, handle, indent=2)
    print(json.dumps(result, indent=2))
