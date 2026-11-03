"""Observe both RAW DMA channels, extended paired tables and actual producers.

This layers new read-only coverage over r50/r49. It changes neither firmware nor
device admission. Missing counters and absent RAM remain explicit unknowns.
"""
import argparse
from contextlib import redirect_stdout
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch

import trace_z62_mode_pipeline as pipeline
import z62_mode_pipeline_snapshot as core

VERSION = '2026.11.03-mode-inputs-r51'
read, words = core.read, core.words


def capture(memory):
    result = core.capture(memory)
    formatter0 = read(memory, 0x20068508, 0x318)
    raw_channels = []
    for channel in (0, 1, 3):
        fields = (8, *range(0x50, 0x70, 4))
        if channel == 0:
            fields += (0x14, 0x18, 0x3c, 0x40, 0x44, 0x48, 0x4c)
        if channel == 3:
            fields += (0x80,)
        base = 0x20069800+channel*0x100
        raw_channels.append({'channel': channel, 'base': hex(base),
                             'fields': {hex(offset): words(read(memory, base+offset, 4))[0]
                                        for offset in fields}})
    result.update(input_view_version=VERSION,
                  other_frontend_address='0x20068508', other_frontend_318=formatter0.hex(),
                  other_raw_dma_channels=raw_channels,
                  paired_raw_800=read(memory, 0x20380000, 0x800).hex(),
                  additional_input_controls={hex(address): words(read(memory, address, 4))[0]
                      for address in (0x2006800c, 0x20068014, 0x20068100,
                                      0x20068260, 0x20068270)},
                  other_frontend_semantics_verified=False)
    return result


def collect_counters(machine, cache):
    row = {'known': False, 'snapshots_atomic': False, 'input': {}, 'stream': {}, 'errors': []}
    def get(path, name, expected):
        try:
            value = machine.qmp.command('qom-get', {'path': path, 'property': name})
            if type(value) is not expected or (expected is int and value < 0):
                raise ValueError('Unexpected producer property type')
            return value
        except (OSError, RuntimeError, ValueError) as exc:
            row['errors'].append({'path': path, 'property': name,
                                  'type': type(exc).__name__, 'message': str(exc)})
            return None
    with machine.io:
        for name in ('raw-accepted', 'raw-rejected', 'raw-bytes',
                     'continuous-attempts', 'continuous-frames', 'continuous-batches',
                     'continuous-rejected', 'continuous-blocked', 'continuous-index', 'continuous-source'):
            row['input'][name] = get('/machine/master-input', name, int)
        for name in ('raw-reason', 'continuous-reason'):
            row['input'][name] = get('/machine/master-input', name, str)
        if 'stream' not in cache:
            paths = []
            for obj in machine.qmp.command('qom-list', {'path': '/machine/unattached'}):
                if obj['type'] == 'child<nikon-z72-boot-config>':
                    path = '/machine/unattached/'+obj['name']
                    if get(path, 'master-role', bool) is True:
                        paths.append(path)
            if len(paths) != 1:
                raise ValueError('Expected exactly one master producer')
            cache['stream'] = paths[0]
        for name in ('raw-stream-active', 'z62-raw-stream'):
            row['stream'][name] = get(cache['stream'], name, bool)
        for name in ('raw-stream-attempts', 'raw-stream-frames', 'raw-stream-failed',
                     'raw-stream-blocked', 'raw-stream-unrelated', 'grid-source-events',
                     'grid-groups', 'grid-rejected', 'preview-batches', 'preview-rejected'):
            row['stream'][name] = get(cache['stream'], name, int)
        for name in ('grid-reason', 'preview-reason'):
            row['stream'][name] = get(cache['stream'], name, str)
    row['known'] = not row['errors']
    return row


def run(output, card, group23, qemu, duration=55):
    output = Path(output)
    original = pipeline.parent.baseline.run
    counters, cache = [], {}
    next_sample = 0
    sources = {str(Path(p)): hashlib.sha256(Path(p).read_bytes()).hexdigest()
               for p in (__file__, pipeline.__file__, core.__file__)}

    def instrument(*args, **kwargs):
        observe = kwargs['extra_observation_hook']
        def sampled(machine, row):
            nonlocal next_sample
            value = observe(machine, row)
            if row['virtual_seconds'] >= next_sample:
                counter = collect_counters(machine, cache)
                counter['virtual_seconds'] = row['virtual_seconds']
                counters.append(counter)
                next_sample = row['virtual_seconds']+2
                print('INPUT_PRODUCERS', json.dumps(counter), flush=True)
            return value
        kwargs['extra_observation_hook'] = sampled
        return original(*args, **kwargs)

    with patch.object(pipeline, 'snapshot', sys.modules[__name__]), \
         patch.object(pipeline, 'VERSION', VERSION), \
         patch.object(pipeline.parent.baseline, 'run', instrument):
        result = pipeline.run(output, card, group23, qemu, duration)
    events = result['selector_events']
    for row in counters:
        row['selector_phase'] = sum(e['virtual_seconds'] <= row['virtual_seconds'] for e in events)
    unchanged = all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == h for p,h in sources.items())
    known_phases = {r['selector_phase'] for r in counters if r['known']}
    receipt = {'schema': 1, 'version': VERSION, 'sources_sha256': sources,
               'sources_unchanged_during_run': unchanged,
               'parent_completed_capture': result['completed_capture'],
               'completed_observation': bool(result['completed_capture'] and unchanged and
                                              known_phases == {0, 1, 2}),
               'counter_samples': counters, 'qemu_sha256': result['qemu_sha256'],
               'process_closed': result['process_closed'], 'camera_accessed': False,
               'firmware_or_software_state_written': False, 'completion_irq_injected': False,
               'mode_recovery_verified': result['recovery_assessment']['recovery_observed'],
               'whole_camera_verified': False}
    with (output/'inputs.json').open('x', encoding='utf-8') as handle:
        json.dump(receipt, handle, indent=2)
    print(json.dumps({'completed_observation': receipt['completed_observation'],
                      'producer_samples': len(counters), 'known_phases': sorted(known_phases)}), flush=True)
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--card', type=Path, required=True)
    parser.add_argument('--group23', type=Path, required=True)
    parser.add_argument('--qemu', type=Path, default=pipeline.parent.host.DEFAULT_QEMU)
    parser.add_argument('--duration', type=float, default=55)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.with_name(args.output.name+'-stdout.txt').open('x', encoding='utf-8') as log:
        with redirect_stdout(pipeline.parent.Tee(sys.stdout, log)):
            receipt = run(args.output, args.card, args.group23, args.qemu.resolve(), args.duration)
    raise SystemExit(0 if receipt['completed_observation'] else 1)
