"""Add bounded data-path snapshots to the frozen r49 selector experiment."""
import argparse
from contextlib import redirect_stdout
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch

import trace_z62_grid_lifecycle as parent
import z62_mode_pipeline_snapshot as snapshot

VERSION = snapshot.VERSION


def run(output, card, group23, qemu, duration=55):
    output = Path(output)
    if output.exists():
        raise FileExistsError('Existing pipeline evidence is immutable')
    original_run = parent.baseline.run
    phase = {'index': 0, 'level': None, 'counts': {0: 0, 1: 0, 2: 0}}
    profiles = {}
    errors = []

    def instrument(*args, **kwargs):
        prior_hit = kwargs['extra_hit_hook']
        prior_observe = kwargs['extra_observation_hook']

        def hit(remote, registers):
            data = prior_hit(remote, registers)
            if (registers['pc'] not in parent.WAIT_POINTS or
                    phase['counts'][phase['index']] >= 8):
                return data
            stage = data.get('stage_resource_wait', {})
            if not stage.get('source_instruction_matches') or not stage.get('work_available'):
                return data
            try:
                # Old work may still retire after the input edge. Repeated old
                # commands must not consume the entire new-mode capture budget.
                commands = tuple(snapshot.words(snapshot.read(remote, address, 12))
                                 for address in (0x20102600, 0x20102640))
                key = (phase['index'], *(word for group in commands for word in group))
                if profiles.get(key, 0) >= 2:
                    return data
                profiles[key] = profiles.get(key, 0)+1
                phase['counts'][phase['index']] += 1
                value = snapshot.capture(remote)
                value.update(selector_phase_observed=phase['index'],
                             selector_level_observed=phase['level'],
                             operation_type_channel_raw=stage.get('operation_type_channel_raw'),
                             stopped_pc=hex(registers['pc']), memory_view='gdb-selected-cpu')
                data['mode_pipeline_snapshot'] = value
                print('MODE_PIPELINE', json.dumps({'phase': phase['index'],
                      'raw_dimensions_fields': [value['raw']['width_field_high16'],
                                                value['raw']['height_field_high16']],
                      'commands': value['command_groups']}), flush=True)
            except (OSError, RuntimeError, ValueError) as exc:
                failure = {'phase': phase['index'], 'pc': hex(registers['pc']),
                           'type': type(exc).__name__, 'message': str(exc)}
                errors.append(failure)
                data['mode_pipeline_snapshot_error'] = failure
            return data

        def observe(machine, row):
            result = prior_observe(machine, row)
            with machine.io:
                level = machine.qmp.command('qom-get', {
                    'path': '/machine/peripheral/keys', 'property': 'input-levels'})
            if type(level) is not int or not 0 <= level <= 0xffffff:
                raise ValueError('Invalid external selector readback')
            level &= 1
            if phase['level'] is not None and level != phase['level']:
                phase['index'] += 1
                if phase['index'] > 2:
                    raise ValueError('Unexpected additional selector transition')
            phase['level'] = level
            return result

        kwargs.update(extra_hit_hook=hit, extra_observation_hook=observe)
        return original_run(*args, **kwargs)

    with patch.object(parent.baseline, 'run', instrument):
        lifecycle = parent.run(output, card, group23, qemu, duration, True)
    trace = json.loads((output/'trace.json').read_text(encoding='utf-8'))
    captures = [{'sequence': hit['sequence'], 'virtual_seconds': hit['state']['virtual_seconds'],
                 'thread': hit['thread'], **hit['extra_observation']['mode_pipeline_snapshot']}
                for hit in trace['hits'] if 'mode_pipeline_snapshot' in hit.get('extra_observation', {})]
    phases = {c['selector_phase_observed'] for c in captures}
    completed = bool(lifecycle['completed'] and phases == {0, 1, 2} and not errors)
    result = {'schema': 1, 'version': VERSION, 'completed_capture': completed,
              'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'snapshot_reader_sha256': hashlib.sha256(Path(snapshot.__file__).read_bytes()).hexdigest(),
              'qemu_sha256': lifecycle['qemu_sha256'],
              'capture_phases': sorted(phases), 'captures': captures, 'read_errors': errors,
              'selector_events': lifecycle['events'], 'recovery_assessment': lifecycle['assessment'],
              'process_closed': lifecycle.get('process_closed'),
              'firmware_or_software_state_written': False, 'completion_irq_injected': False,
              'physical_selector_identity_verified': False, 'whole_camera_verified': False}
    with (output/'pipeline.json').open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2)
    print(json.dumps({'completed_capture': completed, 'capture_phases': sorted(phases),
                      'captures': len(captures), 'read_errors': errors}), flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--card', type=Path, required=True)
    parser.add_argument('--group23', type=Path, required=True)
    parser.add_argument('--qemu', type=Path, default=parent.host.DEFAULT_QEMU)
    parser.add_argument('--duration', type=float, default=55)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.with_name(args.output.name+'-stdout.txt').open('x', encoding='utf-8') as log:
        with redirect_stdout(parent.Tee(sys.stdout, log)):
            receipt = run(args.output, args.card, args.group23, args.qemu.resolve(), args.duration)
    raise SystemExit(0 if receipt['completed_capture'] else 1)
