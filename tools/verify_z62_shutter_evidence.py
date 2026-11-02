"""Verify corrected input semantics without relabelling the old r9 EXIT failure."""
import argparse
import hashlib
import json
from pathlib import Path
from PIL import Image
import run_z62_preview as host
from verify_z62_preview_evidence import expected_lcd_pixel
from probe_z62_shutter_cycle import verify_dwell
import z62_shutter_input_v2 as shutter

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'analysis/z62-isp-r10'


def check():
    build = host.verify_build(host.DEFAULT_QEMU.resolve())
    evidence = {}
    def read(relative):
        data = (BASE / relative).read_bytes()
        evidence[relative] = hashlib.sha256(data).hexdigest()
        return json.loads(data)

    descriptors = read('input-descriptors/trace.json')
    if not descriptors.get('process_closed') or not descriptors.get('live_anchors_verified'):
        raise ValueError('Controller descriptor capture incomplete')
    entries = descriptors['hits'][0]['extra_observation']['descriptors']
    for index, mask in ((9, '0x2'), (11, '0x2000'), (12, '0x4000'), (13, '0x8000')):
        if entries[index]['port'] != '0x40021800' or entries[index]['pin_mask'] != mask:
            raise ValueError('Original controller GPIO descriptor mismatch')
    stop = read('stop-waits/trace.json')
    if not stop.get('process_closed') or stop['summary']['waits']:
        raise ValueError('Unexpected stop-wait observation')
    notifications = [h for h in stop['hits'] if h['label'] == 'image-client-notification'
                     and h['registers']['r0'] == '0x421930e6']
    if len(notifications) != 2:
        raise ValueError('Bank stop notifications incomplete')

    results = {}
    for name, switch in (('no-keys-45', None), ('menu-g14', 0x08000000),
                         ('menu-g1', 0x80000000), ('menu-pin0-matched', 0)):
        report = read(name + '/report.json')
        session = read(name + '/session.json')
        if session['capcom_device']['binary_sha256'] != build['binary_sha256']:
            raise ValueError('Control used another binary: ' + name)
        if (not report.get('observation_completed') or not report.get('clean_exit') or
                report.get('guest_software_patched') or report.get('raw_transactions') or
                report.get('metadata_events')):
            raise ValueError('Incomplete or injected control: ' + name)
        samples = report['samples']
        final = samples[-1]
        if final['virtual_seconds'] < 45 or any(s.get('observation_error') for s in samples):
            raise ValueError('Incomplete observation interval: ' + name)
        if switch is not None:
            if not any(s.get('index') == 1 for s in samples):
                raise ValueError('Menu was not entered: ' + name)
            events = report['external_input_probe']['events']
            if (len(events) != 3 or abs(events[0]['virtual_seconds']-20) > .5 or
                    abs(events[1]['virtual_seconds']-28) > .5 or
                    not 1 <= events[2]['virtual_seconds']-events[1]['virtual_seconds'] <= 1.4):
                raise ValueError('Input schedule differs: ' + name)
            if switch and not any(int(s['capture']['input_route_probe']['switch_words'][0], 16) & switch
                                  for s in samples if 'capture' in s):
                raise ValueError('Original half-press decoder not observed: ' + name)
        rows = [s for s in samples if s.get('virtual_seconds', 0) >= 34 and s.get('index') == 3]
        if not rows or rows[-1]['virtual_seconds']-rows[0]['virtual_seconds'] < 5:
            raise ValueError('Insufficient post-input shooting dwell: ' + name)
        stats = [s['capture']['preview_status']['engines']['master'] for s in rows]
        progressing = stats[-1]['preview-batches'] > stats[0]['preview-batches']
        if any(s['preview-rejected'] for s in stats) or progressing != (switch != 0):
            raise ValueError('Comparison did not reproduce the expected distinction: ' + name)
        if progressing:
            frame = report['frames'][-1]
            png = BASE / name / frame['file']
            if hashlib.sha256(png.read_bytes()).hexdigest() != frame['sha256']:
                raise ValueError('LCD frame identity changed')
            with Image.open(png) as image:
                image = image.convert('RGB')
                for y in (200, 300, 400, 500):
                    for x in (200, 400, 600, 800):
                        if image.getpixel((x, y)) != expected_lcd_pixel(x, y):
                            raise ValueError('Post-input LCD preview pixels differ: ' + name)
        full_press_seen = any(int(s.get('capture', {}).get('input_route_probe', {}).get(
            'switch_words', ['0'])[0], 16) & 0x40000000 for s in samples)
        if switch == 0x80000000 and not full_press_seen:
            raise ValueError('Expected preserved mixed-input evidence was not found')
        results[name] = {'final_seconds': final['virtual_seconds'],
                         'first_dwell_batches': stats[0]['preview-batches'],
                         'last_dwell_batches': stats[-1]['preview-batches'],
                         'preview_progresses': progressing, 'body_full_press_observed': full_press_seen,
                         'drains': stats[-1]['preview-drains'], 'flushes': stats[-1]['preview-flushes']}
    cycle = read('shutter-cycle-v2/report.json')
    if cycle.get('input_adapter') != shutter.identity():
        raise ValueError('Cycle input adapter source changed')
    dwell = verify_dwell(cycle, 2)
    switches = [int(r['capture']['input_switch_words'][0], 16) for r in cycle['samples']
                if 'input_switch_words' in r.get('capture', {})]
    if (not dwell['preview_after_half_press_verified'] or not cycle.get('isolated_half_press_verified')
            or not any(w & 0x80000000 for w in switches) or any(w & 0x40000000 for w in switches)):
        raise ValueError('Repeated half-press cycle failed')
    main_bytes = (ROOT/'start-z6ii-qemu.cmd').read_bytes()
    main_changed = b'run_z62_shutter_preview.py' in main_bytes
    entry_names = ['entry-v2', 'candidate-entry-v2'] + (['main-entry'] if main_changed else [])
    for name in entry_names:
        entry = read(name + '/report.json')
        if (not entry.get('completed') or not entry.get('process_closed') or entry.get('forced_cleanup')
                or not entry.get('half_press_http_verified') or
                entry['status'].get('input_adapter') != shutter.identity()):
            raise ValueError('HTTP adapter acceptance failed: ' + name)
        if name.startswith('candidate') and entry['status'].get('firmware_health_known') is not False:
            raise ValueError('Candidate health was inferred without validation')
        if entry['status']['preview_status']['engines']['master'].get('z62-preview') is not True:
            raise ValueError('Preview model disabled in entry: ' + name)
    return {'schema': 1, 'binary_sha256': build['binary_sha256'], 'input_adapter': shutter.identity(),
            'evidence_sha256': evidence, 'controls': results, **dwell,
            'old_expander0_resume_fixed': False, 'complete_emulator': False,
            'flash_safety_verified': False, 'arbitrary_isp_nodes_supported': False,
            'main_entry_changed': main_changed,
            'main_entry_sha256': hashlib.sha256(main_bytes).hexdigest()}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path)
    args = p.parse_args()
    result = check()
    if args.output:
        with args.output.open('x', encoding='utf-8') as stream:
            json.dump(result, stream, indent=2)
    print(json.dumps(result, indent=2))
