"""Native scene mailbox/DMA tests, with no firmware and CPUs kept stopped."""
import argparse
import base64
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import tempfile
import time

from PIL import Image

import probe_z62_functional_raw as raw
from probe_z62_transaction import close_owned_session
from run_z62_scene_source import DEFAULT_QEMU, verify_build
from z62_scene_packet import make_packet, parse_packet


def require(condition, message):
    if not condition:
        raise ValueError(message)


@contextmanager
def session(binary, enabled=True, initial=None, file_transport=False):
    with tempfile.TemporaryDirectory(dir=os.environ.get('PI_SCRATCH_DIR'), prefix='z62-scene-native-') as folder:
        qmp_port, wire_port = raw.free_port(), raw.free_port()
        command = [str(binary.resolve()), '-M', 'nikon-z62-dual-lab', '-smp', '4,maxcpus=5',
                   '-display', 'none', '-serial', 'none', '-monitor', 'none', '-nic', 'none', '-S',
                   '-qmp', f'tcp:127.0.0.1:{qmp_port},server=on,wait=off',
                   '-qtest', f'tcp:127.0.0.1:{wire_port},server=on,wait=off', '-qtest-log', 'NUL',
                   '-global', 'nikon-z72-input-config.functional-raw=on']
        if enabled:
            command += ['-global', 'nikon-z72-input-config.scene-source=on']
        if initial is not None:
            # The native Windows runtime already uses ASCII staging for all
            # firmware/data command-line paths. Preserve that same contract.
            staged = Path(folder) / 'initial.scene'
            if not str(staged).isascii():
                raise ValueError('Set PI_SCRATCH_DIR to an ASCII ordinary directory')
            packet = Path(initial).read_bytes()
            parse_packet(packet)
            staged.write_bytes(packet)
            command += ['-global', 'nikon-z72-input-config.scene-initial-file=' + staged.as_posix()]
        with (Path(folder) / 'qemu.log').open('xb') as log:
            process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=log)
        s, streams, sockets = raw.Session(), [], []
        ready = False
        try:
            sock = raw.connect(qmp_port, process)
            sockets.append(sock)
            sock.settimeout(20)
            s.qmp = sock.makefile('rwb')
            streams.append(s.qmp)
            json.loads(s.qmp.readline())
            s.query('qmp_capabilities')
            ready = True
            sock = raw.connect(wire_port, process)
            sockets.append(sock)
            sock.settimeout(20)
            s.wire = sock.makefile('rwb')
            streams.append(s.wire)
            s.command, s.irqs = command, []
            s.file_transport, s.mailbox, s.file_sequence = file_transport, Path(folder), 0
            s.publish_seconds = []
            s.access('irq_intercept_out /machine/master-input raw-complete')
            yield s
        except Exception as exc:
            detail = (Path(folder) / 'qemu.log').read_text(encoding='utf-8', errors='replace')
            if detail:
                raise RuntimeError(str(exc) + '\nQEMU: ' + detail[-12000:]) from exc
            raise
        finally:
            close_owned_session(process, s, streams, sockets, ready)


def upload(s, packet, *, error=False):
    if s.file_transport:
        s.file_sequence += 1
        path = s.mailbox / f'frame-{s.file_sequence}.scene'
        path.write_bytes(packet)
        prop, value = 'scene-file', path.as_posix()
    else:
        prop, value = 'scene-packet', base64.b64encode(packet).decode('ascii')
    start = time.monotonic()
    result = s.query('qom-set', {'path': raw.MASTER, 'property': prop, 'value': value}, error=error)
    s.publish_seconds.append(time.monotonic() - start)
    return result


def check_preload(binary, output, packet):
    initial = output / 'initial-scene.bin'
    initial.write_bytes(packet)
    info, pixels = parse_packet(packet)
    with session(binary, initial=initial.resolve()) as s:
        require(s.get('scene-publish-id') == info['publish_id'] and s.get('scene-uses') == 0,
                'Initial file did not load atomically')
        s.configure()
        s.submit()
        s.verify_slots(pixels)
    return {'preloaded_frame_before_guest_execution': True, 'initial_file_ascii_staged': True}


def checks(binary, output, file_transport=False):
    white = make_packet(Image.new('RGB', (64, 64), 'white'), epoch=0x62, publish_id=7,
                        frame_id=3, virtual_time_ns=100_000_000)
    red = make_packet(Image.new('RGB', (64, 64), (255, 0, 0)), epoch=0x62, publish_id=8,
                      frame_id=6, virtual_time_ns=200_000_000)
    white_pixels, red_pixels = white[88:], red[88:]
    result = {}
    with session(binary, file_transport=file_transport) as s:
        require(not s.query('query-status')['running'], 'CPU unexpectedly running')
        s.configure()
        s.fill()
        s.submit()
        require(s.get('raw-last-reason') == 'scene-missing' and s.get('raw-accepted') == 0 and not s.irqs,
                'Missing scene forged a RAW completion')
        s.verify_slots(b'\xa5' * raw.SIZE, guards=True)
        upload(s, white)
        require(s.get('scene-valid') and s.get('scene-publish-id') == 7 and s.get('scene-uses') == 0,
                'Publishing advanced the DMA consumption state')
        s.verify_slots(b'\xa5' * raw.SIZE)
        s.submit()
        s.verify_slots(white_pixels, guards=True)
        require(s.get('raw-accepted') == 1 and s.get('scene-used-publish-id') == 7 and
                s.get('scene-used-epoch') == 0x62 and s.get('scene-used-frame-id') == 3 and
                s.get('scene-used-time-ns') == 100_000_000 and s.get('scene-uses') == 1 and
                s.irqs == ['IRQ raise 0', 'IRQ lower 0'], 'Successful DMA did not own the scene acknowledgement')
        bad = [white, white[:-1], b'BAD!' + red[4:]]
        changed = bytearray(red)
        changed[-2] ^= 1
        bad.append(bytes(changed))
        for offset, value in ((4, 2), (40, 1515), (44, 1007), (48, 2271), (52, 0)):
            changed = bytearray(red)
            struct.pack_into('<I', changed, offset, value)
            bad.append(bytes(changed))
        changed = bytearray(red)
        changed[88 + 2271] = 1
        changed[56:88] = hashlib.sha256(changed[88:]).digest()
        bad.append(bytes(changed))
        for packet in bad:
            upload(s, packet, error=True)
            require(s.get('scene-publish-id') == 7 and s.get('scene-publications') == 1 and
                    s.get('scene-used-publish-id') == 7 and s.get('scene-uses') == 1,
                    'Rejected packet changed the active scene/ack')
        s.submit()
        s.verify_slots(white_pixels)
        require(s.get('scene-uses') == 2 and s.get('scene-repeat-uses') == 1, 'Repeated input was not labelled as a repeat')
        upload(s, red)
        require(s.get('scene-publish-id') == 8 and s.get('scene-used-publish-id') == 7,
                'New input was acknowledged before DMA')
        s.write(0x20069A5C, raw.SLOTS[0] + 4)
        s.submit()
        s.verify_slots(white_pixels)
        require(s.get('scene-used-publish-id') == 7 and s.get('scene-uses') == 2 and len(s.irqs) == 4,
                'Rejected descriptor advanced input or emitted completion')
        s.configure()
        s.submit()
        s.verify_slots(red_pixels)
        require(s.get('scene-used-publish-id') == 8 and s.get('scene-uses') == 3, 'Next valid DMA did not consume the new frame')
        for name in ('scene-epoch', 'scene-publish-id', 'scene-used-frame-id', 'scene-uses'):
            s.query('qom-set', {'path': raw.MASTER, 'property': name, 'value': 0}, error=True)
        s.query('system_reset')
        require(s.get('scene-publish-id') == 8 and s.get('scene-valid') and s.get('scene-uses') == 0,
                'Reset did not preserve external input and clear consumption counters')
        s.configure()
        s.submit()
        s.verify_slots(red_pixels)
        require(s.get('scene-uses') == 1 and s.get('scene-used-publish-id') == 8,
                'Source did not work after reset')
        require(not s.query('query-status')['running'], 'CPU ran during native source test')
        result.update(four_slots_exact=True, missing_input_no_completion=True, publish_not_dma=True,
                      rejected_packets=len(bad), rejection_preserves_active_frame=True,
                      dma_failure_no_ack=True, source_replacement_consumed=True,
                      read_only_acks=True, repeats_explicit=True, reset_preserves_external_frame=True,
                      no_cpu_execution=True, white_raw_sha256=hashlib.sha256(white_pixels).hexdigest(),
                      red_raw_sha256=hashlib.sha256(red_pixels).hexdigest(),
                      native_publish_wall_seconds=s.publish_seconds)
    with session(binary, enabled=False, file_transport=file_transport) as s:
        upload(s, white, error=True)
        s.configure()
        s.submit()
        s.verify_slots(raw.pattern())
        require(s.get('scene-uses') == 0, 'Disabled source affected the legacy RAW path')
        result['default_off_preserves_legacy_pixels'] = True
    result.update(check_preload(binary, output, white))
    return result


def run(binary, output, parent_negative=False, preload_only=False, file_transport=False):
    output.mkdir(parents=True, exist_ok=False)
    result = {'schema': 1, 'completed': False, 'implementation_level': 'C', 'firmware_executed': False,
              'camera_accessed': False, 'preload_only': preload_only,
              'transport': 'file-mailbox' if file_transport else 'base64',
              'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest()}
    try:
        if parent_negative:
            with session(binary, enabled=False) as s:
                error = (s.query('qom-set', {'path': raw.MASTER, 'property': 'scene-file', 'value': 'missing.scene'}, error=True)
                         if file_transport else s.query('qom-get', {'path': raw.MASTER, 'property': 'scene-uses'}, error=True))
                require('not found' in error['desc'], 'Parent kernel unexpectedly exposes the new source')
                result.update(expected_parent_negative=True, missing_property=error['desc'])
        else:
            if file_transport:
                from run_z62_scene_file import verify_build as verify_file_build
                verify_file_build(binary)
            else:
                verify_build(binary)
            if preload_only:
                packet = make_packet(Image.new('RGB', (64, 64), 'white'), epoch=0x62, publish_id=7,
                                     frame_id=3, virtual_time_ns=100_000_000)
                result.update(check_preload(binary, output, packet), completed=True)
            else:
                result.update(checks(binary, output, file_transport), completed=True)
    except Exception as exc:
        result['failure'] = {'type': type(exc).__name__, 'message': str(exc)}
    with (output / 'report.json').open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2)
    print(json.dumps(result, indent=2))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qemu', type=Path, default=DEFAULT_QEMU)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--parent-negative', action='store_true')
    parser.add_argument('--preload-only', action='store_true')
    parser.add_argument('--file-transport', action='store_true')
    args = parser.parse_args()
    result = run(args.qemu, args.output, args.parent_negative, args.preload_only, args.file_transport)
    raise SystemExit(0 if result.get('completed') or result.get('expected_parent_negative') else 1)
