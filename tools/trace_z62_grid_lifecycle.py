"""Exercise the recovered sustained selector input on frozen r48, without guest patches.

This does not identify the physical photo/video lever. Recovery requires original
readiness, LCD enable and both numerical pipelines advancing after restoration.
"""
import argparse
from contextlib import redirect_stdout
import hashlib
import json
import math
from pathlib import Path
import sys
from unittest.mock import patch

import probe_z62_no_lens as baseline
import run_z62_continuous_stats as statistics
import run_z62_grid as host
import run_z62_raw_boundary as boundary
import trace_z62_stage_resource_waits as resources
import z62_selector_observation as selector

VERSION = '2026.11.02-grid-lifecycle-r49'
ROOT = Path(__file__).resolve().parents[1]
READY_CALLBACK = 0x10322B50
WAIT_POINTS = (0x102694AE, 0x102694B2)


def assess(samples, events):
    times = [s['virtual_seconds'] for s in samples]
    if any(type(t) not in (int, float) or not math.isfinite(t) for t in times) or any(
            a > b for a, b in zip(times, times[1:])):
        raise ValueError('Lifecycle samples require finite monotone guest time')
    result = {'initial_ready': False, 'recovery_observed': False,
              'advancing_pair_seconds': None, 'late_known_samples': 0}
    if len(events) != 2 or [e['level'] for e in events] != [0, 1]:
        return result
    low, high = [e['virtual_seconds'] for e in events]
    if type(low) not in (int, float) or type(high) not in (int, float) or not (
            math.isfinite(low) and math.isfinite(high) and low < high):
        raise ValueError('Selector transitions require finite ordered guest time')

    def ready(s):
        return (s.get('known') is True and s.get('display_enabled') is True and
                s.get('index') == 3 and s.get('ready_join') == 3 and s.get('input_inhibit') == 0 and
                all(type(s.get(k)) is int and s[k] > 0 for k in ('grid_groups', 'preview_batches')))

    before = [s for s in samples if s['virtual_seconds'] < low]
    result['initial_ready'] = bool(before and ready(before[-1]))
    late = [s for s in samples if s['virtual_seconds'] >= high+6]
    result['late_known_samples'] = sum(s.get('known') is True for s in late)
    if not result['initial_ready'] or len(late) < 2 or not all(ready(s) for s in late[-2:]):
        return result
    a, b = late[-2:]
    if (b['virtual_seconds']-a['virtual_seconds'] >= 1 and
            b['grid_groups'] > a['grid_groups'] and b['preview_batches'] > a['preview_batches']):
        result.update(recovery_observed=True, advancing_pair_seconds=[a['virtual_seconds'], b['virtual_seconds']])
    return result


def configure_command(command, grid=True):
    result = statistics.configure_command(boundary.configure_command(command, True), True)
    result = host.parent.configure_command(result, True)
    return host.configure_command(result, grid)


def run(output, card, group23, qemu, duration=55, grid=True):
    if output.exists():
        raise FileExistsError('Existing lifecycle evidence is immutable')
    if type(duration) not in (int, float) or not 55 <= duration <= 90:
        raise ValueError('Require a bounded 55..90 second lifecycle experiment')
    build = host.verify_build(qemu)
    image = (ROOT/'artifacts/z62-reference-1.70/master.bin').read_bytes()
    if hashlib.sha256(image).hexdigest() != 'bb83613121f843d65101da936d942acdc513d86dbd3abc26259d0d870d03f5d4':
        raise ValueError('Requires unchanged original C1.70 master')
    points = {**selector.POINTS, READY_CALLBACK: 'original-bit2-ready-callback',
              **{pc: resources.POINTS[pc] for pc in WAIT_POINTS}}
    anchors = {pc: image[pc-0x10020000:pc-0x10020000+4].hex() for pc in points}
    samples, events, frames, paths = [], [], [], []
    phase, deadline, next_sample = 0, None, 0
    final_frame = False
    plan = (('frame', 'before'), ('level', 0), ('frame', 'pin0-low'),
            ('level', 1), ('frame', 'pin0-high'))
    original_configure = baseline.host.configure_command
    receipt = {'schema': 1, 'profile': VERSION, 'completed': False,
               'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               'qemu_sha256': build['binary_sha256'], 'grid_requested': grid,
               'target_guest_seconds': duration, 'camera_accessed': False,
               'guest_software_written_by_host': False, 'software_event_injected': False,
               'physical_photo_video_identity_verified': False, 'whole_camera_verified': False}

    def configure(command, *args, **kwargs):
        return configure_command(original_configure(command, *args, **kwargs), grid)

    def hit(remote, registers):
        pc = registers['pc']
        if pc not in points:
            return {}
        if remote.read(pc, 4).hex() != anchors[pc]:
            raise ValueError('Original lifecycle instruction differs: '+hex(pc))
        if pc in selector.POINTS:
            return {'selector_route': selector.capture(remote, registers)}
        if pc in WAIT_POINTS:
            return {'stage_resource_wait': resources.capture(remote, registers)}
        return {'ready_callback_original_instruction': anchors[pc]}

    def collect(machine, row):
        sample = {'virtual_seconds': row['virtual_seconds'], 'known': False,
                  'index': row['index'], 'display_enabled': row['display_enabled'],
                  'before_control_step': True}
        try:
            with machine.io:
                if not paths:
                    for obj in machine.qmp.command('qom-list', {'path': '/machine/unattached'}):
                        if obj['type'] == 'child<nikon-z72-boot-config>':
                            path = '/machine/unattached/'+obj['name']
                            if machine.qmp.command('qom-get', {'path': path, 'property': 'master-role'}):
                                paths.append(path)
                    if len(paths) != 1:
                        raise ValueError('Expected one owned master processing device')
                counts = {}
                for name in ('grid-groups', 'grid-outputs', 'grid-rejected', 'grid-source-events',
                             'preview-batches', 'preview-result-batches'):
                    value = machine.qmp.command('qom-get', {'path': paths[0], 'property': name})
                    if type(value) is not int or value < 0:
                        raise ValueError('Invalid processing counter: '+name)
                    counts[name] = value
                for name in ('grid-reason', 'preview-reason'):
                    counts[name] = machine.qmp.command('qom-get', {'path': paths[0], 'property': name})
                sample.update(input_inhibit=machine._words(0xC1821EB8, 1)[0],
                              ready_join=machine._words(0xC1868AE8, 1)[0],
                              grid_groups=counts['grid-groups'], preview_batches=counts['preview-batches'],
                              counts=counts, known=True)
        except (OSError, RuntimeError, ValueError) as exc:
            sample['error'] = {'type': type(exc).__name__, 'message': str(exc)}
        samples.append(sample)
        return sample

    def frame(machine, row, name):
        data = machine.frame_png()
        with (output/(name+'.png')).open('xb') as handle:
            handle.write(data)
        frames.append({'file': name+'.png', 'sha256': hashlib.sha256(data).hexdigest(),
                       'virtual_seconds': row['virtual_seconds'], 'index': row['index'],
                       'display_enabled': row['display_enabled']})

    def observe(machine, row):
        nonlocal phase, deadline, next_sample, final_frame
        now = row['virtual_seconds']
        current = None
        if now >= next_sample or (deadline is not None and now >= deadline and phase < len(plan)):
            current = collect(machine, row)
            next_sample = now+1.5
        if deadline is None:
            if (now < 30 or current is None or not current['known'] or row['index'] != 3 or
                    current['input_inhibit'] != 0 or current['ready_join'] != 3):
                return None
            deadline = now
        if phase < len(plan) and now >= deadline:
            action, value = plan[phase]
            if action == 'frame':
                frame(machine, row, value)
                deadline = now+.5
            else:
                with machine.io:
                    args = {'path': '/machine/peripheral/keys', 'property': 'input-levels'}
                    before = machine.qmp.command('qom-get', args)
                    if type(before) is not int or not 0 <= before <= 0xFFFFFF:
                        raise ValueError('Invalid external selector levels')
                    after = (before & ~1) | value
                    machine.qmp.command('qom-set', {**args, 'value': after})
                    if machine.qmp.command('qom-get', args) != after:
                        raise ValueError('External selector readback mismatch')
                event = {'kind': 'persistent-selector-pin0', 'level': value,
                         'virtual_seconds': now, 'before_levels': before, 'after_levels': after}
                events.append(event)
                print('SELECTOR_PIN0', json.dumps(event), flush=True)
                deadline = now+8
            phase += 1
        if phase == len(plan) and not final_frame and now >= duration-.5:
            frame(machine, row, 'final')
            final_frame = True
        return None

    try:
        with patch.object(baseline.host, 'DEFAULT_QEMU', qemu), \
             patch.object(baseline.host, 'configure_command', configure), \
             patch.object(baseline.route.capture.trace, 'observe_capture', lambda machine: {}), \
             patch.object(baseline.route, 'preview_status', lambda machine: {}):
            record, fixture = baseline.run(output, card, group23, True, False, duration,
                extra_points=points, extra_hit_hook=hit, extra_observation_hook=observe,
                extra_state={0x20102000: 1, 0x20102100: 1, 0x20102600: 3, 0x20102640: 3},
                max_stops=1200, automatic_shutter=False, wall_limit=1800,
                observation_timeout_recovery=True)
        receipt.update(completed=bool(fixture['observation_completed'] and phase == len(plan) and
                                      final_frame and record.get('process_closed') and not record.get('failure')),
                       original_waits=resources.correlate(record),
                       original_ready_callback_hits=sum(h['registers']['pc'] == hex(READY_CALLBACK) for h in record['hits']),
                       final_state=record['observations'][-1],
                       process_closed=record.get('process_closed'), detach=record.get('detach'))
    except Exception as exc:
        receipt['failure'] = {'type': type(exc).__name__, 'message': str(exc)}
    receipt.update(samples=samples, events=events, frames=frames, completed_plan_steps=phase,
                   assessment=assess(samples, events))
    if not output.exists():
        output.mkdir(parents=True)
    with (output/'lifecycle.json').open('x', encoding='utf-8') as handle:
        json.dump(receipt, handle, indent=2)
    print(json.dumps({key: receipt.get(key) for key in
                     ('completed', 'grid_requested', 'assessment', 'failure')}), flush=True)
    return receipt


class Tee:
    def __init__(self, *streams):
        self.streams = streams

    def write(self, data):
        for stream in self.streams:
            stream.write(data)
        return len(data)

    def flush(self):
        for stream in self.streams:
            stream.flush()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--card', type=Path, required=True)
    parser.add_argument('--group23', type=Path, required=True)
    parser.add_argument('--qemu', type=Path, default=host.DEFAULT_QEMU)
    parser.add_argument('--duration', type=float, default=55)
    parser.add_argument('--without-grid', action='store_true')
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.with_name(args.output.name+'-stdout.txt').open('x', encoding='utf-8') as log:
        with redirect_stdout(Tee(sys.stdout, log)):
            result = run(args.output, args.card, args.group23, args.qemu.resolve(), args.duration, not args.without_grid)
    raise SystemExit(0 if result['completed'] else 1)
