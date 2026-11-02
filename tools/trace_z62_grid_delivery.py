"""Read-only original C1.70 bank0 numerical output and resource-wait observation."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
from unittest.mock import patch

import run_z62_grid as host
import trace_z62_stage_resource_waits as resources
import trace_z62_transfer_bindings as transfer

VERSION = '2026.11.02-grid-delivery-r48'


def oracle(planes):
    if len(planes) != 3 or any(len(p) != 5120 for p in planes):
        raise ValueError('Require three complete 60x40 row128 u16 planes')
    result = bytearray(3840)
    for y in range(40):
        values = [struct.unpack_from('<60H', p, y*128) for p in planes]
        if any(v > 4095 for row in values for v in row):
            raise ValueError('Not a 12-bit numerical input')
        for x in range(0, 60, 2):
            a, b = (round(sum(row[xx] for row in values)/3) for xx in (x, x+1))
            packed = a | (b << 12)
            result[y*96+x//2*3:y*96+x//2*3+3] = packed.to_bytes(3, 'little')
    return bytes(result)


def pixels(memory):
    def read(address, size):
        data = memory.read(address, size)
        if not isinstance(data, bytes) or len(data) != size:
            raise ValueError('Incomplete original bank0 data snapshot')
        return data

    table = struct.unpack('<64I', read(0x20102200, 256))
    frames = []
    for index in range(4):
        source, target = table[index*16+1:index*16+3]
        delta = source-0x88EDF000
        if delta < 0 or delta % 0x36000 or delta//0x36000 >= 6:
            raise ValueError('Original source is outside the observed RGB ring')
        if target & 15 or not 0x8AEBC400 <= target <= 0x8D000000-3840:
            raise ValueError('Original packed output is outside the observed output pool')
        planes = [read(source+c*0x12000, 5120) for c in range(3)]
        actual = read(target, 3840)
        expected = oracle(planes)
        frames.append({'frame': index, 'source': hex(source), 'source_slot': delta//0x36000,
                       'target': hex(target), 'input_planes_hex': [p.hex() for p in planes],
                       'actual_packed_hex': actual.hex(),
                       'actual_sha256': hashlib.sha256(actual).hexdigest(),
                       'expected_sha256': hashlib.sha256(expected).hexdigest(),
                       'all_samples_match_current_input': actual == expected,
                       'all_row_padding_zero': all(actual[y*96+90:y*96+96] == b'\0'*6 for y in range(40))})
    return {'read_only': True, 'snapshots_atomic': False, 'frames': frames,
            'all_four_match_current_input': all(f['all_samples_match_current_input'] for f in frames),
            'algorithm_level': 'C', 'nikon_math_equivalence_verified': False}


def counts(memory):
    raw = memory.read(0xC1864864, 40)
    if not isinstance(raw, bytes) or len(raw) != 40:
        raise ValueError('Incomplete original bank command counters')
    words = struct.unpack('<10I', raw)
    return {'raw_28': raw.hex(), 'bank0_commands': words[1], 'bank0_skip': words[8],
            'bank1_commands': words[2], 'bank1_skip': words[7]}


def run(output, card, group23, qemu, duration):
    if output.exists():
        raise FileExistsError('Existing grid observation is immutable')
    if not 12 <= duration <= 30:
        raise ValueError('Require a bounded 12..30 second original firmware observation')
    build = host.verify_build(qemu)
    root = Path(__file__).resolve().parents[1]
    image = (root/'artifacts/z62-reference-1.70/master.bin').read_bytes()
    if hashlib.sha256(image).hexdigest() != 'bb83613121f843d65101da936d942acdc513d86dbd3abc26259d0d870d03f5d4':
        raise ValueError('Requires unchanged original C1.70 master')
    points = {**resources.POINTS, transfer.IRQ_SAMPLE: 'native-irq102-grid-status'}
    anchors = {**resources.ANCHORS, transfer.IRQ_SAMPLE: transfer.ANCHORS[transfer.IRQ_SAMPLE]}
    for pc, data in anchors.items():
        if image[pc-0x10020000:pc-0x10020000+4].hex() != data:
            raise ValueError('Original grid delivery instruction differs: '+hex(pc))
    profiles = resources.signals.waits.profiles
    baseline = resources.signals.waits.selector.probe.baseline
    original_configure = baseline.host.configure_command
    pixel_snapshots = []

    def configure(command, *args, **kwargs):
        command = original_configure(command, *args, **kwargs)
        command = profiles.statistics.configure_command(profiles.boundary.configure_command(command, True), True)
        command = host.parent.configure_command(command, True)
        return host.configure_command(command, True)

    def hit(remote, registers):
        pc = registers['pc']
        result = {}
        if pc in resources.POINTS:
            result['stage_resource_wait'] = resources.capture(remote, registers)
        if pc == transfer.IRQ_SAMPLE:
            data = transfer.capture(remote, registers)
            result['grid_transfer_status'] = data
            if data['source_instruction_matches'] and data['native_status20'] & 4 and len(pixel_snapshots) < 2:
                snapshot = pixels(remote)
                pixel_snapshots.append(snapshot)
                result['grid_pixels_snapshot_index'] = len(pixel_snapshots)-1
        if pc in (*resources.SOURCE_POINTS, 0x10263D34):
            result['grid_native_counts'] = counts(remote)
        return result

    paths = []
    def diagnostics(machine):
        if not paths:
            objects = machine.qmp.command('qom-list', {'path': '/machine/unattached'})
            for obj in objects:
                if obj['type'] == 'child<nikon-z72-boot-config>':
                    path = '/machine/unattached/'+obj['name']
                    if machine.qmp.command('qom-get', {'path': path, 'property': 'master-role'}):
                        paths.append(path)
            if len(paths) != 1:
                raise ValueError('Expected one owned master grid device')
        names = ('grid-groups', 'grid-outputs', 'grid-bytes', 'grid-rejected',
                 'grid-source-events', 'grid-reason', 'preview-result-batches')
        return {'grid_counters': {name: machine.qmp.command('qom-get',
                    {'path': paths[0], 'property': name}) for name in names}}

    with patch.object(baseline.host, 'DEFAULT_QEMU', qemu), \
         patch.object(baseline.host, 'configure_command', configure), \
         patch.object(baseline.route.capture.trace, 'observe_capture', lambda machine: {}), \
         patch.object(baseline.route, 'preview_status', diagnostics):
        trace, fixture = baseline.run(output, card, group23, True, False, duration,
            extra_points=points, extra_hit_hook=hit, max_stops=5000, automatic_shutter=False,
            wall_limit=1200, observation_timeout_recovery=True)
    analysis = resources.correlate(trace)
    status = [h for h in trace['hits'] if 'grid_transfer_status' in h.get('extra_observation', {})]
    callbacks = [h for h in trace['hits'] if int(h['registers']['pc'], 16) == resources.SOURCE_ENTRY
                 and h.get('extra_observation', {}).get('stage_resource_wait', {}).get('notification_code_raw') == 0x42193081
                 and h['extra_observation']['stage_resource_wait']['notification_payload_raw'] & 1]
    callback_counts = [h['extra_observation']['grid_native_counts'] for h in callbacks]
    publications = [e for e in analysis['producer_points'] if e['snapshot'].get('target_event_object')
                    and e['snapshot']['signal_mask_raw'] == 0x01000000]
    waits = [w for w in analysis['waits'] if w['call']['snapshot']['api'] == 'stage-69446']
    returned = [w for w in waits if w['return']['snapshot']['return_r0'] == 1
                and w['return']['snapshot'].get('output_bits_known')
                and w['return']['snapshot']['output_bits_raw'] & 0x01000000]
    irq_seen = any(h['extra_observation']['grid_transfer_status'].get('native_status20', 0) & 4 for h in status)
    result = {'schema': 1, 'profile': VERSION,
              'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'qemu_sha256': build['binary_sha256'], 'target_guest_seconds': duration,
              'completed_observation': fixture['observation_completed'], 'analysis': analysis,
              'pixel_snapshots': pixel_snapshots, 'grid_irq_observed': irq_seen,
              'bank0_callback_count': len(callbacks), 'bank0_callback_counts': callback_counts,
              'bank0_skip_decrease_observed': any(a['bank0_skip'] > b['bank0_skip'] for a,b in zip(callback_counts, callback_counts[1:])),
              'bank0_01000000_publications': len(publications),
              'paired_81000000_waits': len(waits), 'returned_with_01000000': len(returned),
              'runtime_software_status_written_by_observer': False, 'guest_functions_called_by_host': False,
              'software_event_injected': False, 'algorithm_level': 'C',
              'full_nikon_eleven_operators_implemented': False, 'mode_recovery_verified': False,
              'whole_camera_verified': False, 'camera_accessed': False}
    with (output/'grid-delivery.json').open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2)
    print(json.dumps({key: result[key] for key in ('completed_observation', 'grid_irq_observed',
        'bank0_callback_count', 'bank0_skip_decrease_observed', 'bank0_01000000_publications',
        'paired_81000000_waits', 'returned_with_01000000')}), flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--card', type=Path, required=True)
    parser.add_argument('--group23', type=Path, required=True)
    parser.add_argument('--qemu', type=Path, default=host.DEFAULT_QEMU)
    parser.add_argument('--duration', type=float, default=12)
    args = parser.parse_args()
    receipt = run(args.output, args.card, args.group23, args.qemu.resolve(), args.duration)
    raise SystemExit(0 if receipt['completed_observation'] and receipt['returned_with_01000000'] else 1)
