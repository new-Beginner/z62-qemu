"""Observe original CPU reads from the first two three-plane statistics slots.

Only native r17 RAW boundaries are enabled. No statistics bytes, result-ready
events, firmware instructions or software flags are supplied by this probe.
"""
import argparse
import json
from pathlib import Path
from unittest.mock import patch

import probe_z62_no_lens as fixture
import run_z62_raw_boundary as host

WATCHES = {base + slot*0x36000 + plane*0x12000: 8
           for base in (0x88EDF000, 0xC8EDF000) for slot in (0, 1) for plane in range(3)}


def context(remote, registers):
    result = {'cpsr': hex(remote.get(remote.regs(), 'cpsr'))}
    pointer = registers['r4']
    if registers['pc'] >= 0x10020000 and 0xC0000000 <= pointer <= 0xDFFFFFC0:
        result['r4_header_64'] = remote.read(pointer, 64).hex()
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--card', type=Path, required=True)
    parser.add_argument('--group23', type=Path, required=True)
    parser.add_argument('--duration', type=float, default=18)
    parser.add_argument('--primary', action='store_true', help='observe sum/count and scalar planes')
    parser.add_argument('--continuous-statistics', action='store_true')
    args = parser.parse_args()
    if not 2 <= args.duration <= 18:
        parser.error('Observation must stop before scheduled shutter inputs')
    watches = WATCHES
    if args.primary:
        watches = {base + alias: 8 for base in (0x88E37000, 0x88E37008, 0x88E73000)
                   for alias in (0, 0x40000000)}
    runtime = host
    if args.continuous_statistics:
        import run_z62_continuous_stats as runtime
    manifest = runtime.verify_build(runtime.DEFAULT_QEMU)
    original = fixture.host.configure_command
    def configure(command, *a, **kw):
        result = host.configure_command(original(command, *a, **kw))
        return runtime.configure_command(result)
    def observe(machine, row):
        if args.continuous_statistics:
            from z62_continuous_stats_status import continuous_stats_status
            with machine.io:
                row.update(continuous_stats_status(machine))
    with patch.object(fixture.host, 'DEFAULT_QEMU', runtime.DEFAULT_QEMU), \
         patch.object(fixture.host, 'configure_command', configure):
        result, receipt = fixture.run(args.output, args.card, args.group23, True, False, args.duration,
                                      read_watchpoints=watches, extra_hit_hook=context,
                                      extra_observation_hook=observe, max_stops=600)
    reads = [h for h in result['hits'] if h['label'] == 'native-ram-read']
    summary = {'observation_completed': receipt['observation_completed'],
               'read_hits': len(reads), 'reader_pcs': sorted({h['registers']['pc'] for h in reads}),
               'host_statistics_data_supplied': False, 'host_result_ready_events_supplied': False,
               'native_statistics_enabled': args.continuous_statistics,
               'native_statistics_identity': manifest['continuous_statistics_device'] if args.continuous_statistics else None,
               'photo_capture_verified': False, 'complete_emulator': False}
    with (args.output / 'reader-summary.json').open('x', encoding='utf-8') as handle:
        json.dump(summary, handle, indent=2)
    print(json.dumps(summary, indent=2))
    raise SystemExit(0 if receipt['observation_completed'] else 1)
