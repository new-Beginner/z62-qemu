"""Observe the original source packets across the unchanged r53 selector case."""
import argparse
from contextlib import redirect_stdout
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch

import trace_z62_photo_results_lifecycle as parent
import trace_z62_grid_lifecycle as lifecycle
import z62_paired_source_snapshot as snapshot

ROOT = Path(__file__).resolve().parents[1]
VERSION = snapshot.VERSION


def coverage(rows):
    return sorted({row['selector_phase'] for row in rows
        if row['snapshot']['kind'] == 'dispatch-entry' and row['snapshot']['bank_byte4'] == 0 and
           row['snapshot']['core']['captured'] is True and row['snapshot']['source']['captured'] is True})


def correlate(rows):
    pending, pairs, incomplete, outside = {}, [], [], []
    for row in rows:
        value, registers = row['snapshot'], row['registers']
        if value['kind'] == 'dispatch-entry':
            continue
        key = (row['thread'], registers['sp']+(16 if value['kind'] == 'geometry-written' else 0))
        if value['kind'] == 'geometry-entry':
            if key in pending:
                incomplete.append({**pending.pop(key), 'reason': 'new call before observed return'})
            pending[key] = row
        else:
            entry = pending.pop(key, None)
            if entry is None:
                outside.append(row)
            elif (registers['r5'] != entry['registers']['r0'] or
                  registers['r6'] != entry['registers']['r1']):
                incomplete.append({'entry': entry, 'return': row, 'reason': 'preserved source frame differs'})
            else:
                pairs.append({'entry': entry, 'return': row})
    incomplete.extend({'entry': row, 'reason': 'observation ended before return'} for row in pending.values())
    return {'pairs': pairs, 'incomplete': incomplete, 'unmatched_returns': outside}


def run(output, card, group23, qemu, duration=55):
    if output.exists():
        raise FileExistsError('Existing paired source evidence is immutable')
    original = lifecycle.baseline.run
    image = (ROOT/'artifacts/z62-reference-1.70/master.bin').read_bytes()
    if hashlib.sha256(image).hexdigest() != 'bb83613121f843d65101da936d942acdc513d86dbd3abc26259d0d870d03f5d4':
        raise ValueError('Requires original C1.70 master')
    anchors = {pc: image[pc-0x10020000:pc-0x10020000+4].hex() for pc in snapshot.POINTS}
    sources = {str(Path(p)): hashlib.sha256(Path(p).read_bytes()).hexdigest()
               for p in (__file__, snapshot.__file__)}
    errors, counts = [], {pc: 0 for pc in anchors}

    def instrument(*args, **kwargs):
        previous = kwargs['extra_hit_hook']

        def hit(remote, registers):
            result = previous(remote, registers)
            pc = registers['pc']
            if pc not in anchors:
                return result
            counts[pc] += 1
            if counts[pc] > 100:
                return {**result, 'paired_source_capture_limit_reached': True}
            if remote.read(pc, 4).hex() != anchors[pc]:
                raise ValueError('Original paired source instruction differs')
            try:
                if pc == snapshot.DISPATCH:
                    data = snapshot.dispatch(remote, registers['r0'], registers['r1'])
                else:
                    after = pc == snapshot.FORMAT_RETURN
                    obj = registers['r5'] if after else registers['r0']
                    address = registers['r6'] if after else registers['r1']
                    data = snapshot.format_packet(remote, obj, address, after=after)
                data.update(source_instruction_4=anchors[pc], source_instruction_matches=True,
                            entry_stack=snapshot.read_packet(remote, registers['sp'], 32))
                result['paired_source_snapshot'] = data
                core = data.get('core', {})
                print('PAIRED_SOURCE', json.dumps({'pc': hex(pc), 'kind': data['kind'],
                    'bank': data['bank_byte4'], 'layout_argument': core.get('layout_argument'),
                    'stride_argument': data.get('source', {}).get('stride_argument'),
                    'paired': data.get('paired_before', data.get('paired_observed'))}), flush=True)
            except (OSError, RuntimeError, ValueError) as exc:
                failure = {'pc': hex(pc), 'type': type(exc).__name__, 'message': str(exc)}
                errors.append(failure)
                result['paired_source_snapshot_error'] = failure
            return result

        kwargs['extra_hit_hook'] = hit
        kwargs['extra_points'] = {**kwargs['extra_points'], **snapshot.POINTS}
        kwargs['max_stops'] = 2400
        return original(*args, **kwargs)

    with patch.object(lifecycle.baseline, 'run', instrument):
        prior = parent.run(output, card, group23, qemu, True, duration)
    trace = json.loads((output/'trace.json').read_text(encoding='utf-8'))
    life = json.loads((output/'lifecycle.json').read_text(encoding='utf-8'))
    rows = []
    for hit in trace['hits']:
        data = hit.get('extra_observation', {}).get('paired_source_snapshot')
        if data is None:
            continue
        now = hit['state']['virtual_seconds']
        rows.append({'sequence': hit['sequence'], 'virtual_seconds': now, 'thread': hit['thread'],
            'selector_phase': sum(e['virtual_seconds'] <= now for e in life['events']),
            'registers': {key: int(value, 16) for key, value in hit['registers'].items()}, 'snapshot': data})
    paired = correlate(rows)
    observed_phases = {row['return']['selector_phase'] for row in paired['pairs']
        if row['return']['snapshot']['geometry_argument_matches_observed'] and
           row['return']['snapshot']['bank_byte4'] == 0}
    source_phases = coverage(rows)
    unchanged = all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == digest for p, digest in sources.items())
    limited = any(value > 100 for value in counts.values())
    receipt = {'schema': 1, 'version': VERSION, 'qemu_sha256': prior['qemu_sha256'],
        'sources_sha256': sources, 'sources_unchanged_during_run': unchanged,
        'completed_observation': bool(prior['completed_observation'] and unchanged and not errors and
            not limited and source_phases == [0, 1, 2] and observed_phases == {0, 1, 2} and
            not paired['incomplete'] and not paired['unmatched_returns']),
        'parent_completed_observation': prior['completed_observation'], 'snapshots': rows,
        'geometry_call_pairs': paired, 'known_geometry_return_phases': sorted(observed_phases),
        'known_dispatch_source_phases': source_phases,
        'hit_counts': {hex(pc): count for pc, count in counts.items()},
        'capture_limit_reached': limited, 'read_errors': errors, 'process_closed': prior['process_closed'],
        'strict_mode_recovery_verified': prior['mode_recovery_verified'],
        'actual_pixel_production_verified': False, 'guest_software_written': False,
        'completion_irq_injected': False, 'camera_accessed': False, 'whole_camera_verified': False}
    with (output/'paired-source.json').open('x', encoding='utf-8') as handle:
        json.dump(receipt, handle, indent=2)
    print(json.dumps({key: receipt[key] for key in ('completed_observation', 'known_geometry_return_phases',
        'known_dispatch_source_phases', 'hit_counts', 'capture_limit_reached', 'read_errors',
        'strict_mode_recovery_verified')}), flush=True)
    return receipt


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
        with redirect_stdout(lifecycle.Tee(sys.stdout, log)):
            result = run(args.output, args.card, args.group23, args.qemu.resolve(), args.duration)
    raise SystemExit(0 if result['completed_observation'] else 1)
