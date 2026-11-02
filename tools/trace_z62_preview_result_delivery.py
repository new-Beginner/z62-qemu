"""Observe real IRQ102 -> original result callback -> native event publication."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
from unittest.mock import patch

import trace_z62_result_subscriptions as subscriptions
import trace_z62_transfer_bindings as transfer
import run_z62_preview_results_format as host

VERSION = '2026.11.02-preview-result-delivery-r47b'
CALLBACK, PUBLICATION = 0x10263D4C, 0x10263F94
ANCHORS = {CALLBACK: '70b57a4c', PUBLICATION: 'f9f0eeb9'}


def capture(memory, registers):
    pc = registers['pc']
    if pc not in ANCHORS:
        raise ValueError('Not an original preview result delivery point')
    def read(address, size):
        data = memory.read(address, size)
        if not isinstance(data, bytes) or len(data) != size:
            raise ValueError('Incomplete native preview result counter snapshot')
        return data
    code = read(pc, 4).hex()
    result = {'read_only': True, 'snapshots_atomic': False,
              'source_instruction_4': code, 'source_instruction_matches': code == ANCHORS[pc]}
    if not result['source_instruction_matches']:
        return result
    raw = read(0xC1864864, 40)
    values = struct.unpack('<10I', raw)
    result.update(kind='native-preview-callback' if pc == CALLBACK else 'native-preview-publication',
                  native_counts_raw_28=raw.hex(), native_result_count_before_or_at_point=values[5],
                  bank0_command_count_raw=values[1], bank1_command_count_raw=values[2],
                  bank0_skip_count_raw=values[8], bank1_skip_count_raw=values[7])
    if pc == CALLBACK:
        result.update(message_code_raw=registers['r0'], argument1_raw=registers['r1'])
    else:
        result.update(event_object_raw=registers['r0'], event_mask_raw=registers['r1'],
                      is_result_event_object=registers['r0'] == 0xC18647EC)
    return result


def run(output, card, group23, qemu, duration):
    if output.exists():
        raise FileExistsError('Existing result delivery evidence is immutable')
    if not 12 <= duration <= 30:
        raise ValueError('Require a 12..30 second bounded result observation')
    build = host.verify_build(qemu)
    root = Path(__file__).resolve().parents[1]
    image = (root/'artifacts/z62-reference-1.70/master.bin').read_bytes()
    if hashlib.sha256(image).hexdigest() != 'bb83613121f843d65101da936d942acdc513d86dbd3abc26259d0d870d03f5d4':
        raise ValueError('Requires original C1.70 master')
    selected = (subscriptions.WAIT, subscriptions.HANDOFF, subscriptions.REGISTER,
                subscriptions.REGISTER_STORED, subscriptions.MASK, subscriptions.MASK_STORED,
                subscriptions.SOURCE)
    points = {pc: subscriptions.POINTS[pc] for pc in selected}
    points.update({transfer.IRQ_SAMPLE: 'native-irq102-result-status',
                   CALLBACK: 'native-preview-result-callback', PUBLICATION: 'native-preview-event-publication'})
    anchors = {pc: subscriptions.ANCHORS[pc] for pc in selected}
    anchors.update({transfer.IRQ_SAMPLE: transfer.ANCHORS[transfer.IRQ_SAMPLE], **ANCHORS})
    for pc, data in anchors.items():
        if image[pc-0x10020000:pc-0x10020000+4].hex() != data:
            raise ValueError('Original result delivery instruction differs: '+hex(pc))
    profiles = subscriptions.resources.signals.waits.profiles
    baseline = subscriptions.resources.signals.waits.selector.probe.baseline
    original_configure = baseline.host.configure_command

    def configure(command, *args, **kwargs):
        command = original_configure(command, *args, **kwargs)
        command = profiles.statistics.configure_command(profiles.boundary.configure_command(command, True), True)
        return host.configure_command(command, True)

    def hit(remote, registers):
        pc = registers['pc']
        if pc in ANCHORS:
            data = capture(remote, registers)
        elif pc == transfer.IRQ_SAMPLE:
            data = transfer.capture(remote, registers)
        elif pc in subscriptions.ANCHORS:
            data = subscriptions.capture(remote, registers)
        else:
            return {}
        return {'preview_result_delivery': data}

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
                raise ValueError('Expected one owned master result device')
        names = ('preview-batches', 'preview-outputs', 'preview-bytes', 'preview-result-batches',
                 'preview-result-units', 'preview-result-rejected')
        return {'preview_result_counters': {name: machine.qmp.command('qom-get',
                    {'path': paths[0], 'property': name}) for name in names}}

    with patch.object(baseline.host, 'DEFAULT_QEMU', qemu), \
         patch.object(baseline.host, 'configure_command', configure), \
         patch.object(baseline.route.capture.trace, 'observe_capture', lambda machine: {}), \
         patch.object(baseline.route, 'preview_status', diagnostics):
        trace, fixture = baseline.run(output, card, group23, True, False, duration,
            extra_points=points, extra_hit_hook=hit, max_stops=5000, automatic_shutter=False,
            wall_limit=1200, observation_timeout_recovery=True)
    observations = [{'sequence': h['sequence'], 'guest_seconds': h['state']['virtual_seconds'],
                     'thread': h['thread'], 'registers': h['registers'],
                     'snapshot': h['extra_observation']['preview_result_delivery']}
                    for h in trace['hits'] if 'preview_result_delivery' in h.get('extra_observation', {})]
    irqs = [x for x in observations if x['snapshot'].get('kind') == 'native-irq102-status']
    callbacks = [x for x in observations if x['snapshot'].get('kind') == 'native-preview-callback'
                 and x['snapshot']['message_code_raw'] == 0x42193082]
    events = [x for x in observations if x['snapshot'].get('is_result_event_object')]
    delivered = (any(x['snapshot']['native_status1c'] & 0x61 == 0x61 for x in irqs)
                 and {x['snapshot']['argument1_raw'] for x in callbacks} >= {1, 2, 4}
                 and {x['snapshot']['event_mask_raw'] for x in events} >= {1, 2, 4}
                 and any(x['snapshot']['native_result_count_before_or_at_point'] >= 3 for x in events))
    result = {'schema': 1, 'profile': VERSION, 'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'qemu_sha256': build['binary_sha256'], 'target_guest_seconds': duration,
              'completed_observation': fixture['observation_completed'], 'observations': observations,
              'result_irq_and_native_callback_publication_observed': delivered,
              'guest_software_written_by_host': False, 'guest_functions_called_by_host': False,
              'software_event_injected': False, 'bank0_numerical_graph_executed': False,
              'whole_camera_verified': False, 'camera_accessed': False}
    with (output/'preview-result-delivery.json').open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2)
    print(json.dumps({'completed_observation': result['completed_observation'],
                      'native_result_delivery_observed': delivered, 'callbacks_82': len(callbacks),
                      'result_publications': len(events)}), flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--card', type=Path, required=True)
    parser.add_argument('--group23', type=Path, required=True)
    parser.add_argument('--qemu', type=Path, default=host.DEFAULT_QEMU)
    parser.add_argument('--duration', type=float, default=12)
    args = parser.parse_args()
    r = run(args.output, args.card, args.group23, args.qemu.resolve(), args.duration)
    raise SystemExit(0 if r['completed_observation'] and r['result_irq_and_native_callback_publication_observed'] else 1)
