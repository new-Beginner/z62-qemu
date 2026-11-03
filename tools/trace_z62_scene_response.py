"""Challenge returned photo liveview with new external pixels on frozen r53.

Only scene mailboxes and the existing selector input are written. Every guest
RAM/MMIO access below is a bounded read in the master CPU's debug view.
"""
import argparse
from contextlib import redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
from unittest.mock import patch

from PIL import Image

import trace_z62_photo_results_lifecycle as parent
import trace_z62_grid_lifecycle as lifecycle
import z62_mode_pipeline_snapshot as memory
import z62_scene_packet as packet
import z62_scene_response as response

VERSION = response.VERSION
EPOCH = 0x54
SOURCE_PROPERTIES = ('scene-used-publish-id', 'scene-used-epoch', 'scene-used-frame-id',
                     'scene-used-time-ns', 'scene-uses', 'raw-accepted')


def read_bytes(machine, address, size):
    if size % 4 or not memory.candidate_ram(address, size):
        raise ValueError('Scene response read outside bounded RAM')
    return struct.pack('<'+'I'*(size//4), *machine._words(address, size//4))


def source_status(machine):
    values = {name: machine.qmp.command('qom-get', {
        'path': '/machine/master-input', 'property': name}) for name in SOURCE_PROPERTIES}
    if any(type(value) is not int or value < 0 for value in values.values()):
        raise ValueError('Invalid actual scene source property')
    if machine.qmp.command('qom-get', {'path': '/machine/master-input',
                                      'property': 'scene-used-publish-id'}) != values['scene-used-publish-id']:
        raise ValueError('Scene generation changed during source read')
    return values


def pixel_evidence(machine):
    fields = machine._words(0x20069518, 2)
    stride = machine._words(0x20069a08, 1)[0]
    if (fields[0] >> 16, fields[1] >> 16, stride) != (1514, 1006, 2272):
        raise ValueError('RAW response requires the observed photo input geometry')
    bank = machine._words(0x20069a3c, 1)[0] & 1
    raw_destinations = machine._words(0x20069a50+bank*16, 4)
    offset = 502*2272+752*3//2
    raw = [{'slot': i, 'address': hex(base+offset),
            'data': read_bytes(machine, base+offset, 48).hex()}
           for i, base in enumerate(raw_destinations)]
    nv12 = []
    for port in (3, 4, 5):
        words = machine._words(0x20100400+port*64, 13)
        width, height = words[8] & 0x7fff, words[8] >> 16
        row_stride, uv_offset = words[4], words[10]
        if (words[0] != 0x09000201 or width not in (1024, 1920) or
                height not in (680, 682, 1080) or row_stride != width or
                not row_stride*height <= uv_offset <= 4*1024*1024):
            raise ValueError('Unrecognized photo NV12 port '+str(port))
        x, y = (width//2) & ~3, (height//2) & ~1
        for slot in range(4):
            base = machine._words(0x20102200+slot*64+port*4, 1)[0]
            y_address, uv_address = base+y*row_stride+x, base+uv_offset+(y//2)*row_stride+x
            nv12.append({'port': port, 'slot': slot, 'base': hex(base),
                         'geometry': [width, height, row_stride, uv_offset],
                         'y_address': hex(y_address), 'uv_address': hex(uv_address),
                         'y': read_bytes(machine, y_address, 32).hex(),
                         'uv': read_bytes(machine, uv_address, 32).hex()})
    return raw, nv12


def run(output, card, group23, qemu, duration=70):
    output = Path(output)
    if output.exists():
        raise FileExistsError('Existing scene response evidence is immutable')
    if not 65 <= duration <= 90:
        raise ValueError('Require a bounded 65..90 second response window')
    original_run = lifecycle.baseline.run
    original_configure = lifecycle.configure_command
    files = (Path(__file__), Path(response.__file__), Path(packet.__file__))
    sources = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    observations, challenges, errors, selector_edges = [], [], [], []
    state = {'level': None, 'return_time': None, 'next_sample': 0,
             'active': None, 'next_id': 2, 'next_gray': 210, 'stream_path': None}

    with tempfile.TemporaryDirectory(dir=os.environ.get('PI_SCRATCH_DIR'),
                                     prefix='z62-response-r54-') as folder:
        folder = Path(folder)
        if not str(folder).isascii():
            raise ValueError('Require an ASCII ordinary scene mailbox directory')
        initial = folder/'initial.scene'
        with initial.open('xb') as handle:
            handle.write(packet.make_packet(Image.new('RGB', (64, 64), (40, 40, 40)),
                epoch=EPOCH, publish_id=1, frame_id=0, virtual_time_ns=0))

        def configure(command, *args, **kwargs):
            return original_configure(command, *args, **kwargs)+[
                '-global', 'nikon-z72-input-config.scene-source=on',
                '-global', 'nikon-z72-input-config.scene-initial-file='+initial.as_posix()]

        def stream(machine):
            if state['stream_path'] is None:
                found = []
                for obj in machine.qmp.command('qom-list', {'path': '/machine/unattached'}):
                    if obj['type'] == 'child<nikon-z72-boot-config>':
                        path = '/machine/unattached/'+obj['name']
                        if machine.qmp.command('qom-get', {'path': path, 'property': 'master-role'}) is True:
                            found.append(path)
                if len(found) != 1:
                    raise ValueError('Expected exactly one master processing device')
                state['stream_path'] = found[0]
            value = machine.qmp.command('qom-get', {'path': state['stream_path'], 'property': 'preview-batches'})
            if type(value) is not int or value < 0:
                raise ValueError('Invalid actual preview counter')
            return value

        def publish(machine, now, gray):
            identifier, time_ns = state['next_id'], int(now*1_000_000_000)
            frame_id = time_ns*30//1_000_000_000
            data = packet.make_packet(Image.new('RGB', (64, 64), (gray, gray, gray)),
                epoch=EPOCH, publish_id=identifier, frame_id=frame_id, virtual_time_ns=time_ns)
            info, raw = packet.parse_packet(data)
            path = folder/('challenge-'+str(identifier)+'.scene')
            with path.open('xb') as handle:
                handle.write(data)
            before = source_status(machine)
            preview = stream(machine)
            active = {**info, 'gray': gray, 'published_virtual_seconds': now,
                      'before_source': before, 'before_preview': preview,
                      'packet_sha256': hashlib.sha256(data).hexdigest(),
                      'raw_reference': raw[502*2272+752*3//2:502*2272+752*3//2+48].hex(),
                      'publication_confirmed': False}
            # Record the attempt before sending. A timeout never retransmits it.
            challenges.append(active)
            state['active'] = active
            machine.qmp.command('qom-set', {'path': '/machine/master-input',
                                          'property': 'scene-file', 'value': path.as_posix()})
            actual = machine.qmp.command('qom-get', {'path': '/machine/master-input', 'property': 'scene-publish-id'})
            if actual != identifier:
                raise ValueError('Scene publish readback differs')
            active['publication_confirmed'] = True
            print('SCENE_CHALLENGE', json.dumps(active), flush=True)

        def instrument(*args, **kwargs):
            prior = kwargs['extra_observation_hook']

            def observe(machine, row):
                result = prior(machine, row)
                now = row['virtual_seconds']
                if now < state['next_sample']:
                    return result
                state['next_sample'] = now+1.5
                try:
                    with machine.io:
                        levels = machine.qmp.command('qom-get', {
                            'path': '/machine/peripheral/keys', 'property': 'input-levels'})
                        if type(levels) is not int or not 0 <= levels <= 0xffffff:
                            raise ValueError('Invalid selector readback')
                        level = levels & 1
                        if state['level'] is not None and level != state['level']:
                            selector_edges.append({'level': level, 'virtual_seconds': now})
                            if [edge['level'] for edge in selector_edges] == [0, 1]:
                                state['return_time'] = now
                        state['level'] = level
                        returned = state['return_time']
                        if returned is None or now < returned+6 or errors:
                            return result
                        if state['active'] is None and len(challenges) < 2:
                            publish(machine, now, state['next_gray'])
                            return result
                        active = state['active']
                        if active is None or now < active['published_virtual_seconds']+2:
                            return result
                        source = source_status(machine)
                        preview = stream(machine)
                        ready = machine._words(0xC1868AE8, 1)[0]
                        inhibit = machine._words(0xC1821EB8, 1)[0]
                        raw, nv12 = pixel_evidence(machine)
                    png = machine.frame_png()
                    image = Image.open(io.BytesIO(png))
                    measurement = response.measure(active['gray'], bytes.fromhex(active['raw_reference']),
                        [bytes.fromhex(r['data']) for r in raw],
                        [{'y': bytes.fromhex(r['y']), 'uv': bytes.fromhex(r['uv'])} for r in nv12], image)
                    name = 'scene-'+str(active['publish_id'])+'-'+str(len(observations))+'.png'
                    with (output/name).open('xb') as handle:
                        handle.write(png)
                    value = {**active, 'observed_virtual_seconds': now, 'source': source,
                        'raw_delta': source['raw-accepted']-active['before_source']['raw-accepted'],
                        'source_uses_delta': source['scene-uses']-active['before_source']['scene-uses'],
                        'preview_delta': preview-active['before_preview'],
                        'index': row['index'], 'display_enabled': row['display_enabled'],
                        'ready_join': ready, 'input_inhibit': inhibit,
                        'raw_patches': raw, 'nv12_patches': nv12, 'measurement': measurement,
                        'lcd_file': name, 'lcd_sha256': hashlib.sha256(png).hexdigest(),
                        'snapshots_atomic': False, 'memory_view': 'master-cpu-virtual-debug-read'}
                    observations.append(value)
                    print('SCENE_RESPONSE', json.dumps({key: value[key] for key in
                        ('publish_id', 'observed_virtual_seconds', 'raw_delta', 'preview_delta', 'measurement')}), flush=True)
                    # A second, contrasting scene is sent even after a negative
                    # first measurement, preserving useful failure evidence.
                    if now >= active['published_virtual_seconds']+5:
                        state['active'] = None
                        state['next_id'] += 1
                        state['next_gray'] = 40
                except (OSError, RuntimeError, ValueError) as exc:
                    failure = {'virtual_seconds': now, 'type': type(exc).__name__, 'message': str(exc)}
                    errors.append(failure)
                    print('SCENE_RESPONSE_ERROR', json.dumps(failure), flush=True)
                return result

            kwargs['extra_observation_hook'] = observe
            return original_run(*args, **kwargs)

        with patch.object(lifecycle, 'configure_command', configure), \
             patch.object(lifecycle.baseline, 'run', instrument):
            previous = parent.run(output, card, group23, qemu, True, duration)
    latest = {r['publish_id']: r for r in observations}
    selected = [latest[c['publish_id']] for c in challenges if c['publish_id'] in latest]
    unchanged = all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == h for p, h in sources.items())
    assessment = response.assess(selected, state['return_time'])
    receipt = {'schema': 1, 'version': VERSION, 'sources_sha256': sources,
        'sources_unchanged_during_run': unchanged, 'qemu_sha256': previous['qemu_sha256'],
        'completed_observation': bool(previous['completed_observation'] and unchanged and not errors and
                                      len(selected) == 2),
        'process_closed': previous['process_closed'], 'source_challenges': challenges,
        'selector_edges_sampled': selector_edges, 'return_time_sampled': state['return_time'],
        'observations': observations, 'selected_observations': selected, 'read_errors': errors,
        'assessment': assessment, 'strict_mode_recovery_verified': previous['mode_recovery_verified'],
        'implementation_level': 'C', 'factory_firmware_executed': True, 'factory_isp_equivalent': False,
        'firmware_or_software_state_written': False, 'completion_irq_injected': False,
        'camera_accessed': False, 'whole_camera_verified': False}
    with (output/'scene-response.json').open('x', encoding='utf-8') as handle:
        json.dump(receipt, handle, indent=2)
    print(json.dumps({k: receipt[k] for k in
        ('completed_observation', 'assessment', 'strict_mode_recovery_verified', 'read_errors')}), flush=True)
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--card', type=Path, required=True)
    parser.add_argument('--group23', type=Path, required=True)
    parser.add_argument('--qemu', type=Path, default=parent.host.DEFAULT_QEMU)
    parser.add_argument('--duration', type=float, default=70)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.with_name(args.output.name+'-stdout.txt').open('x', encoding='utf-8') as log:
        with redirect_stdout(lifecycle.Tee(sys.stdout, log)):
            result = run(args.output, args.card, args.group23, args.qemu.resolve(), args.duration)
    raise SystemExit(0 if result['completed_observation'] else 1)
