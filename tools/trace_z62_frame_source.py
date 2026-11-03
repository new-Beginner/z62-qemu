"""Trace the actual descriptor -> serialized-source boundary on frozen r53."""
import argparse
from contextlib import redirect_stdout
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch

import trace_z62_photo_results_lifecycle as parent
import trace_z62_grid_lifecycle as lifecycle
import z62_frame_source_snapshot as snapshot

ROOT = Path(__file__).resolve().parents[1]
VERSION = snapshot.VERSION


def correlate(rows):
    pending, pairs, incomplete, unmatched = {}, [], [], []
    reverse = {value: key for key, value in snapshot.CONSTRUCTORS.items()}
    for row in rows:
        pc, registers = row['pc'], row['registers']
        after = pc in reverse
        key = (reverse[pc] if after else pc, row['thread'], registers['sp']+(16 if after else 0))
        if not after:
            if key in pending:
                incomplete.append({'entry': pending.pop(key), 'reason': 'reentered same constructor frame'})
            pending[key] = row
            continue
        entry = pending.pop(key, None)
        if entry is None:
            unmatched.append(row)
        elif (registers['r5'] != entry['registers']['r0'] or
              registers['r4']-0xcc != entry['registers']['r1']):
            incomplete.append({'entry': entry, 'return': row, 'reason': 'original preserved frame differs'})
        else:
            pairs.append({'entry': entry, 'return': row})
    incomplete.extend({'entry': row, 'reason': 'observation ended before return'} for row in pending.values())
    return {'pairs': pairs, 'incomplete': incomplete, 'unmatched_returns': unmatched}


def run(output, card, group23, qemu, duration=55):
    if output.exists():
        raise FileExistsError('Existing frame source evidence is immutable')
    image = (ROOT/'artifacts/z62-reference-1.70/master.bin').read_bytes()
    if hashlib.sha256(image).hexdigest() != 'bb83613121f843d65101da936d942acdc513d86dbd3abc26259d0d870d03f5d4':
        raise ValueError('Requires original C1.70 master')
    anchors = {pc: image[pc-0x10020000:pc-0x10020000+4].hex() for pc in snapshot.POINTS}
    sources = {str(Path(p)): hashlib.sha256(Path(p).read_bytes()).hexdigest()
               for p in (__file__, snapshot.__file__)}
    original = lifecycle.baseline.run
    counts, errors = {pc: 0 for pc in anchors}, []

    def instrument(*args, **kwargs):
        previous = kwargs['extra_hit_hook']
        def hit(remote, registers):
            result = previous(remote, registers)
            pc = registers['pc']
            if pc not in anchors:
                return result
            counts[pc] += 1
            if counts[pc] > 100:
                return {**result, 'frame_source_capture_limit_reached': True}
            if remote.read(pc, 4).hex() != anchors[pc]:
                raise ValueError('Original frame source instruction differs')
            try:
                after = pc in snapshot.CONSTRUCTORS.values()
                context = registers['r5'] if after else registers['r0']
                root = registers['r4']-0xcc if after else registers['r1']
                data = snapshot.capture(remote, context, root, after=after)
                data.update(source_instruction_4=anchors[pc], source_instruction_matches=True)
                result['frame_source_snapshot'] = data
                print('FRAME_SOURCE', json.dumps({'pc': hex(pc), 'after': after,
                    'master': data['is_master_root'], 'context': hex(context),
                    'descriptors': [d['layout_fields'] for d in data['descriptors']],
                    'template': data['template_core']['layout_argument'],
                    'serialized': data['serialized_core']['layout_argument'] if data['serialized_core'] else None}), flush=True)
            except (OSError, RuntimeError, ValueError) as exc:
                failure = {'pc': hex(pc), 'type': type(exc).__name__, 'message': str(exc)}
                errors.append(failure)
                result['frame_source_snapshot_error'] = failure
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
        data = hit.get('extra_observation', {}).get('frame_source_snapshot')
        if data is not None:
            now = hit['state']['virtual_seconds']
            rows.append({'pc': int(hit['registers']['pc'], 16), 'thread': hit['thread'],
                'sequence': hit['sequence'], 'virtual_seconds': now,
                'selector_phase': sum(e['virtual_seconds'] <= now for e in life['events']),
                'registers': {key: int(value, 16) for key, value in hit['registers'].items()}, 'snapshot': data})
    paired = correlate(rows)
    known = {p['return']['selector_phase'] for p in paired['pairs']
             if p['return']['snapshot']['is_master_root'] and
                p['return']['snapshot']['all_source_descriptors_captured'] and
                p['return']['snapshot']['serialized_root']['captured'] and
                p['return']['snapshot']['serialized_source']['captured']}
    unchanged = all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == digest for p, digest in sources.items())
    limited = any(value > 100 for value in counts.values())
    receipt = {'schema': 1, 'version': VERSION, 'qemu_sha256': prior['qemu_sha256'],
        'sources_sha256': sources, 'sources_unchanged_during_run': unchanged,
        'completed_observation': bool(prior['completed_observation'] and unchanged and not errors and not limited and
            known == {0, 1, 2} and not paired['incomplete'] and not paired['unmatched_returns']),
        'parent_completed_observation': prior['completed_observation'], 'snapshots': rows,
        'constructor_pairs': paired, 'known_master_descriptor_phases': sorted(known),
        'hit_counts': {hex(pc): n for pc, n in counts.items()}, 'capture_limit_reached': limited,
        'read_errors': errors, 'process_closed': prior['process_closed'],
        'strict_mode_recovery_verified': prior['mode_recovery_verified'],
        'actual_pixel_production_verified': False, 'guest_software_written': False,
        'completion_irq_injected': False, 'camera_accessed': False, 'whole_camera_verified': False}
    with (output/'frame-source.json').open('x', encoding='utf-8') as handle:
        json.dump(receipt, handle, indent=2)
    print(json.dumps({key: receipt[key] for key in ('completed_observation', 'known_master_descriptor_phases',
        'hit_counts', 'capture_limit_reached', 'read_errors', 'strict_mode_recovery_verified')}), flush=True)
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
