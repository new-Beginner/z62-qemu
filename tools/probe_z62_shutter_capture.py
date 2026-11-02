"""Observe actual two-stage shutter and firmware writes to a new virtual SD.

Creates its own blank FAT32 regular file in an ASCII scratch folder. Only that
file receives guest writes; it is preserved after QEMU exits for forensic reads.
No existing card, firmware, software event or camera connection is modified.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

import probe_z62_liveview as base
import probe_z62_preview_firmware as preview
import z62_shutter_input_v2 as shutter
import z62_qmp_transport as monitor
from z62_virtual_sd import create_fat32, digest
from reference_updates import replace_once


def run(output, full_press=True, *, wait_for_ready=False, duration=50, wall_limit=1800):
    if output.exists():
        raise FileExistsError('Existing capture evidence is protected')
    scratch = os.environ.get('PI_SCRATCH_DIR') or tempfile.gettempdir()
    if not str(scratch).isascii() or shutil.disk_usage(scratch).free < 6 * 1024**3:
        raise ValueError('Need an ASCII scratch directory with at least 6 GiB free')
    card_work = Path(tempfile.mkdtemp(prefix='z62-capture-card-', dir=scratch))
    card = card_work / 'capture.raw'
    media = create_fat32(card, 4096)
    media.update(initial_sha256=digest(card), owner='this-probe-new-blank-file',
                 writes_persisted=True, physical_media_accessed=False)
    original_apply, original_observe = base.host.host.apply_console, base.observe_capture
    phase = 0
    events = []
    times = None if wait_for_ready else (20, 21, 21.5, 22)
    readiness_receipt = None
    inputs = ((1, 0), (13, 0), (13, 1), (1, 1))

    def apply(source, persistent=False):
        original_apply(source, persistent)
        shutter.apply_console(source)
        monitor.apply_console(source)
        path = source / 'tools/z62_console.py'
        text = replace_once(path.read_text(encoding='utf-8'),
                            'format=raw,snapshot=on', 'format=raw,snapshot=off')
        path.write_text(text, encoding='utf-8', newline='\n')

    def observe(machine):
        nonlocal phase, times, readiness_receipt
        capture = original_observe(machine)
        ticks, frequency = machine._key_clock()
        now = ticks / frequency
        inhibit = machine._words(0xC1821EB8, 1)[0]
        joined = machine._words(0xC1868AE8, 1)[0]
        foreground = machine._words(0xC1811E60, 1)[0] & 255
        readiness = {'input_inhibit':inhibit,'ready_join':joined,'foreground':foreground,
                     'operation_queue_words':[hex(w) for w in machine._words(0xC23D9F14,5)]}
        if wait_for_ready and times is None and now >= 17 and inhibit == 0 and joined == 3 and foreground == 3:
            readiness_receipt = {**readiness,'virtual_seconds':now}
            times = (now+.5, now+1.5, now+2, now+2.5)
            print('ORIGINAL_READY', json.dumps(readiness_receipt), flush=True)
        capture['shutter_capture_probe'] = {
            'virtual_seconds': now, 'phase': phase,
            'switch_words': [hex(w) for w in machine._words(0xC25D6FC0, 3)],
            'readiness': readiness,
            'monitor_transport': machine.qmp.diagnostics(),
            'blockstats': machine.qmp.command('query-blockstats'),
            'image_command_banks': [hex(w) for w in machine._words(0x20102000, 7)] +
                                   [hex(w) for w in machine._words(0x20102100, 7)],
        }
        if times is not None and phase < len(times) and now >= times[phase]:
            pin, level = inputs[phase]
            if full_press or pin != 13:
                machine._qtest(f'set_irq_in /machine/controller/keys-gpio unnamed-gpio-in {pin} {level}')
            event = {'phase': phase, 'virtual_seconds': now, 'gpio_g_pin': pin,
                     'level': level, 'driven': full_press or pin != 13,
                     'switch_words_before': capture['shutter_capture_probe']['switch_words']}
            events.append(event)
            print('SHUTTER_INPUT', json.dumps(event), flush=True)
            phase += 1
        return capture

    base.host.host.apply_console, base.observe_capture = apply, observe
    try:
        result = preview.run(output, duration, wall_limit, sd_card=card)
    finally:
        base.host.host.apply_console, base.observe_capture = original_apply, original_observe
    media['final_sha256'] = digest(card)
    media['changed'] = media['initial_sha256'] != media['final_sha256']
    result['shutter_capture_experiment'] = {
        'full_press_requested': full_press, 'events': events, 'virtual_media': media,
        'waited_for_original_ready':wait_for_ready,'readiness_receipt':readiness_receipt,
        'input_adapter': shutter.identity(), 'photo_saved_verified': False,
        'monitor_transport': monitor.identity(),
        'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    (output / 'report.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print('VIRTUAL_MEDIA', json.dumps(media), flush=True)
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--half-only', action='store_true')
    args = p.parse_args()
    result = run(args.output, not args.half_only)
    print('observation_completed=', result['observation_completed'])
    raise SystemExit(0 if result['observation_completed'] else 1)
