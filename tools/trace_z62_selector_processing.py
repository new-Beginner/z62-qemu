"""Controlled selector comparison with existing DMA-backed r17/r18 models.

Same original GPIO/queue experiment and frozen r21 binary; only two processing
properties differ. Counter samples are non-atomic, read-only observations.
"""
import argparse
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import trace_z62_selector_ready_queue as parent
import run_z62_analog_input as hardware
import run_z62_raw_boundary as boundary
import run_z62_continuous_stats as statistics
from z62_raw_stream_status import raw_stream_status
from z62_continuous_stats_status import continuous_stats_status
from z62_preview_status import preview_status

VERSION = '2026.11.01-selector-processing-profile-r32'


def run(output, card, group23, *, enabled=True):
    if output.exists():
        raise FileExistsError('Existing evidence is immutable')
    build = hardware.verify_build()
    fixture = parent.parent.probe.baseline
    original_configure = fixture.host.configure_command
    original_route = fixture.route.run
    samples = []
    next_read = 1.0
    final_read = False
    receipt = {'schema': 1, 'profile': VERSION, 'completed': False,
               'native_processing_requested': enabled, 'qemu_sha256': build['binary_sha256'],
               'raw_boundary_model': boundary.device.identity(),
               'continuous_statistics_model': statistics.device.identity(),
               'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               'camera_accessed': False, 'guest_software_written_by_host': False,
               'physical_photo_video_identity_verified': False, 'mode_recovery_verified': False}

    def configure(command, *args, **kwargs):
        result = original_configure(command, *args, **kwargs)
        return statistics.configure_command(boundary.configure_command(result, enabled), enabled)

    def instrumented(*args, **kwargs):
        original_observe = kwargs.get('extra_observation_hook')

        def observe(machine, row):
            nonlocal next_read, final_read
            event = original_observe(machine, row) if original_observe else None
            now = row['virtual_seconds']
            if now < next_read and (now < 54 or final_read):
                return event
            next_read = now + 5
            final_read |= now >= 54
            sample = {'guest_seconds_at_row': now, 'after_input_hook': True, 'known': False}
            try:
                with machine.io:
                    sample['raw'] = raw_stream_status(machine)['raw_stream_status']
                    sample['continuous'] = continuous_stats_status(machine)['continuous_statistics_status']
                    sample['preview'] = preview_status(machine)['preview_status']
                    banks = {}
                    for item in machine.qmp.command('qom-list', {'path': '/machine/unattached'}):
                        if item['type'] != 'child<nikon-z72-boot-config>':
                            continue
                        path = '/machine/unattached/' + item['name']
                        master = machine.qmp.command('qom-get', {'path': path, 'property': 'master-role'})
                        if type(master) is not bool:
                            raise ValueError('Unexpected engine role')
                        values = {}
                        for prop in ('raw-boundary-events', 'raw-boundary-coalesced'):
                            value = machine.qmp.command('qom-get', {'path': path, 'property': prop})
                            if type(value) is not int or value < 0:
                                raise ValueError('Unexpected RAW boundary counter')
                            values[prop] = value
                        banks['master' if master else 'slave'] = values
                    sample['boundary'] = banks
                    sample['known'] = (set(banks) == {'master', 'slave'} and
                                       all(sample[key]['known'] for key in ('raw', 'continuous', 'preview')))
            except (OSError, RuntimeError, ValueError) as exc:
                sample['error'] = {'type': type(exc).__name__, 'message': str(exc)}
            samples.append(sample)
            return event

        kwargs['extra_observation_hook'] = observe
        return original_route(*args, **kwargs)

    try:
        with patch.object(fixture.host, 'configure_command', configure), \
             patch.object(fixture.route, 'run', instrumented):
            result = parent.run(output, card, group23)
        trace = json.loads((output / 'trace.json').read_text(encoding='utf-8'))
        last = trace['observations'][-1]
        receipt.update(completed=result['completed'], samples=samples,
                       final_display_enabled=last.get('display_enabled'),
                       final_ready_join=last['extra_words']['0xc1868ae8'][0],
                       callback_hits=result['ready_callback_hits'],
                       enqueues=result['enqueues'])
    except Exception as exc:
        receipt.update(samples=samples, failure={'type': type(exc).__name__, 'message': str(exc)})
    if not output.exists():
        output.mkdir(parents=True)
    with (output / 'processing.json').open('x', encoding='utf-8') as handle:
        json.dump(receipt, handle, indent=2)
    print(json.dumps({key: receipt.get(key) for key in
                     ('completed', 'native_processing_requested', 'final_display_enabled',
                      'final_ready_join', 'failure')}), flush=True)
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--card', type=Path, required=True)
    parser.add_argument('--group23', type=Path, required=True)
    parser.add_argument('--legacy-processing', action='store_true')
    args = parser.parse_args()
    raise SystemExit(0 if run(args.output, args.card, args.group23,
                             enabled=not args.legacy_processing)['completed'] else 1)
