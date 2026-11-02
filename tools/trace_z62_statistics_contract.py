"""Recover original continuous statistics configuration and buffer consumers.

Uses native r17 ingress boundaries only; never supplies result-ready IRQs or
changes software fields. Captures bounded configuration and pointed RAM headers.
"""
import argparse
import json
from pathlib import Path
from unittest.mock import patch

import probe_z62_no_lens as fixture
import run_z62_raw_boundary as host

POINTS = {0x10239EA2: 'statistics-config', 0x1020C894: 'statistics-grid-group',
          0x1020C89E: 'statistics-extra-group', 0x1020C8B2: 'statistics-dma-format',
          0x1020C8BE: 'statistics-dma-layout', 0x1020C8F0: 'statistics-dma-bank',
          0x1023AE34: 'parameter-commit', 0x102CF658: 'statistics-buffer-acquire'}
STATE = {0xC26A0468: 16, 0xC26A04A0: 98, 0xC26A060C: 85,
         0xC26A0054: 38, 0xC269FA04: 2, 0x2006A200: 93}
for ch in range(5):
    base = 0x2006A400 + ch*0x100
    fields = [(0x14, 2), (0x24, 1), (0x3C, 6), (0x60, 1), (0x80, 1)]
    # Only the multi-plane channels accept the extra destination registers.
    if ch >= 2:
        fields.extend(((0x54, 3), (0x64, 3)))
    for offset, count in fields:
        STATE[base+offset] = count


def context(remote, registers):
    pc = registers['pc']
    if pc not in POINTS:
        return {}
    result = {}
    if pc in (0x1020C8B2, 0x1020C8BE):
        pointer, size = registers['r1'], 32
    elif pc in (0x1020C894, 0x1020C89E):
        pointer, size = registers['r0'], 96
    elif pc == 0x102CF658:
        pointer, size = registers['r1'], 76
        result['frame_object'] = hex(registers['r0'])
    else:
        pointer, size = registers['r0'], 128
    if 0xC0000000 <= pointer <= 0xE0000000-size:
        result.update(pointer=hex(pointer), descriptor=remote.read(pointer, size).hex())
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--card', type=Path, required=True)
    parser.add_argument('--group23', type=Path, required=True)
    parser.add_argument('--continuous-statistics', action='store_true')
    args = parser.parse_args()
    runtime = host
    if args.continuous_statistics:
        import run_z62_continuous_stats as runtime
    manifest = runtime.verify_build(runtime.DEFAULT_QEMU)
    original = fixture.host.configure_command
    def configure(command, *a, **kw):
        return runtime.configure_command(host.configure_command(original(command, *a, **kw)))
    def observe(machine, row):
        if args.continuous_statistics:
            from z62_continuous_stats_status import continuous_stats_status
            with machine.io:
                row.update(continuous_stats_status(machine))
    with patch.object(fixture.host, 'DEFAULT_QEMU', runtime.DEFAULT_QEMU), \
         patch.object(fixture.host, 'configure_command', configure):
        result, _ = fixture.run(args.output, args.card, args.group23, True, True, 3,
                                extra_points=POINTS, extra_state=STATE,
                                extra_hit_hook=context, extra_observation_hook=observe, max_stops=1000)
    complete = bool(result.get('capture_setup_observed') and result.get('process_closed') and
                    result.get('detach') == 'OK' and result.get('stop_reason') == 'virtual limit' and
                    not result.get('failure') and not result.get('cleanup_error') and
                    result['observations'][-1]['virtual_seconds'] >= 3 and not result.get('shutter_contacts'))
    summary = {'observation_completed': complete, 'counts': result['summary']['counts'],
               'native_statistics_identity': manifest['continuous_statistics_device'] if args.continuous_statistics else None,
               'complete_emulator': False}
    with (args.output / 'contract-summary.json').open('x', encoding='utf-8') as handle:
        json.dump(summary, handle, indent=2)
    print(json.dumps(summary, indent=2))
    raise SystemExit(0 if complete else 1)
