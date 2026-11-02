"""Trace frame-event delivery and submit waits; optional single IRQ-route test.

The optional input-event0 pulse is a diagnostic after verified native RAW DMA,
not an implemented hardware source. Never installed in normal launchers, never
writes software flags, messages or registers, and never claims image completion.
"""
import argparse
import json
from pathlib import Path
from unittest.mock import patch

import probe_z62_no_lens as fixture
from probe_z62_no_lens import run
from trace_z62_capture_setup import _raw_backed_event_diagnostic

CALLS = {0x102335E0: 'event8', 0x1023382C: 'event5',
         0x10233836: 'input-buffers', 0x10233B14: 'frame-process-a',
         0x10233B1C: 'frame-process-b', 0x10233B38: 'frame-process-c'}
POINTS = {0x10238FF2: 'input-bank0-callback', 0x10238B8A: 'input-worker',
          0x1022F17A: 'frame-source-callback'}
for address, name in CALLS.items():
    POINTS[address] = name + '-call'
    POINTS[address+4] = name + '-return'


def context(remote, registers):
    if registers['pc'] == 0x1023AE42:
        pointer = registers['r1']
        if not 0xC0000000 <= pointer <= 0xDFFFFFE0:
            raise ValueError('Expected original RAM input-parameter pointer table')
        table = remote.read(pointer, 32)
        descriptors = []
        for i in range(8):
            p = int.from_bytes(table[i*4:i*4+4], 'little')
            item = {'index': i, 'address': hex(p)}
            if 0xC0000000 <= p <= 0xDFFFFF80:
                data = remote.read(p, 128)
                item['bytes_128'] = data.hex()
                if i == 2:
                    headers = []
                    for offset in (0x2C, 0x30, 0x34, 0x38, 0x3C, 0x40):
                        header = int.from_bytes(data[offset:offset+4], 'little')
                        if 0xC0000000 <= header <= 0xDFFFFF80:
                            headers.append({'pointer_offset': hex(offset), 'address': hex(header),
                                            'bytes_128': remote.read(header, 128).hex()})
                    item['resource_headers'] = headers
            descriptors.append(item)
        return {'parameter_mask': hex(registers['r0']), 'pointer_table_32': table.hex(),
                'parameter_descriptors': descriptors}
    if registers['pc'] == 0x10238FF2:
        pointer = registers['r1']
        if 0xC0000000 <= pointer <= 0xDFFFFFE0:
            return {'input_irq_payload_32': remote.read(pointer, 32).hex()}
    return {}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--card', type=Path, required=True)
    parser.add_argument('--group23', type=Path, required=True)
    parser.add_argument('--pulse', action='store_true')
    parser.add_argument('--native-boundary', action='store_true')
    parser.add_argument('--continuous-statistics', action='store_true')
    parser.add_argument('--ready-details', action='store_true')
    args = parser.parse_args()
    if args.pulse and (args.native_boundary or args.continuous_statistics):
        parser.error('Do not mix a manual IRQ experiment with the native source')
    if args.ready_details:
        POINTS.update({0x1023AE42: 'input-parameter-update',
                       0x10238804: 'input-ready-call', 0x10238808: 'input-ready-return',
                       0x1023AE34: 'input-parameter-commit'})
    pulses = []
    def observe(machine, row):
        if args.continuous_statistics:
            from z62_continuous_stats_status import continuous_stats_status
            with machine.io:
                row.update(continuous_stats_status(machine))
        if not args.pulse or pulses or row['virtual_seconds'] < 1.4:
            return None
        with machine.io:
            result = _raw_backed_event_diagnostic(machine, (0,))
        if result:
            result.update(kind='single-input-event0-route-test', virtual_seconds=row['virtual_seconds'])
            pulses.append(result)
        return result
    def execute():
        return run(args.output, args.card, args.group23, True, True, 3,
                   extra_points=POINTS, extra_state={0xC1887CB0: 48, 0xC1888080: 20},
                   extra_hit_hook=context, extra_observation_hook=observe, max_stops=800)
    native = None
    boundary_identity = None
    if args.native_boundary or args.continuous_statistics:
        if args.continuous_statistics:
            import run_z62_continuous_stats as native_host
            boundary_identity = native_host.parent.device.identity()
        else:
            import run_z62_raw_boundary as native_host
            boundary_identity = native_host.device.identity()
        native = native_host.verify_build(native_host.DEFAULT_QEMU)
        original_configure = fixture.host.configure_command
        def configure(command, *a, **kw):
            result = original_configure(command, *a, **kw)
            if args.continuous_statistics:
                result = native_host.parent.configure_command(result)
            return native_host.configure_command(result)
        with patch.object(fixture.host, 'DEFAULT_QEMU', native_host.DEFAULT_QEMU), \
             patch.object(fixture.host, 'configure_command', configure):
            result, _ = execute()
    else:
        result, _ = execute()
    complete = bool(result.get('capture_setup_observed') and result.get('stop_reason') == 'virtual limit'
                    and result.get('process_closed') and result.get('detach') == 'OK'
                    and not result.get('failure') and not result.get('cleanup_error')
                    and result['observations'][-1]['virtual_seconds'] >= 3
                    and not result.get('shutter_contacts') and len(pulses) == int(args.pulse))
    summary = {'observation_completed': complete, 'pulse_requested': args.pulse, 'pulses': pulses,
               'counts': result['summary']['counts'], 'hardware_source_implemented': native is not None,
               'native_boundary_identity': boundary_identity,
               'continuous_statistics_identity': native['continuous_statistics_device'] if args.continuous_statistics else None,
               'photo_capture_verified': False, 'complete_emulator': False}
    with (args.output / 'delivery-summary.json').open('x', encoding='utf-8') as handle:
        json.dump(summary, handle, indent=2)
    print(json.dumps(summary, indent=2))
    raise SystemExit(0 if complete else 1)
