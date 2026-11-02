"""Run original menu/preview cycles with the new absent-lens two-stage input."""
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch

import probe_z62_shutter_cycle_v2 as cycle
import run_z62_preview as preview
import run_z62_capture_contacts as contacts
import z62_shutter_input_v2 as shutter
import z62_capture_input as capture_input
import z62_lens_contact as lens
import z62_qmp_transport as monitor


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--group23', type=Path, required=True)
    own, rest = parser.parse_known_args()
    fixture = own.group23.resolve(strict=True)
    expected = 'c7dd14358b45b2813fdee85fc587bcdd5899f7a81e0d5830513d631235bcc700'
    if not str(fixture).isascii() or ',' in str(fixture) or hashlib.sha256(fixture.read_bytes()).hexdigest() != expected:
        raise ValueError('Unrecognized experimental NOR23 fixture')
    args = cycle.prior.transaction.parse_args(['--qemu', str(contacts.DEFAULT_QEMU)] + rest)
    contacts.verify_build(args.qemu)
    args.raw_stream = args.input_drain = args.paired_sync = args.capcom_sync = True
    if not args.functional_raw or not args.raw_completion:
        raise ValueError('functional-raw and raw-completion required')
    original_configure, original_apply = preview.configure_command, shutter.apply_console
    timing = cycle.prior.transaction.timing
    original_observe = timing.observe_capture
    def configure(command, *a, **kw):
        result = contacts.configure_command(original_configure(command, *a, **kw), True)
        return result + ['-device', f'loader,file={fixture},addr=0x13420000,force-raw=on']
    def apply(source):
        original_apply(source)
        lens.apply_console(source)
        capture_input.apply_console(source)
        monitor.apply_console(source)
    def observe(machine):
        return {**original_observe(machine), 'capture_input': machine._capture_input_status()}
    with patch.object(preview, 'configure_command', configure), \
         patch.object(shutter, 'apply_console', apply), \
         patch.object(timing, 'observe_capture', observe):
        result = cycle.run(args)
    result.update(input_adapter=capture_input.identity(), lens_contact=lens.identity(),
                  group23={'path': str(fixture), 'sha256': expected, 'factory_calibration': False})
    (args.output / 'report.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print({k: result[k] for k in ('isolated_half_press_verified', 'dwells')})
    raise SystemExit(0 if result['isolated_half_press_verified'] else 1)
