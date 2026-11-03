"""Regression: an unconsumed old RAW notification must not starve a new C request."""
import argparse
import hashlib
import json
from pathlib import Path
import probe_z62_paired_ingress as native
import run_z62_paired_ingress as host


def snapshot(s):
    return {'raw_frames': native.stream.get(s, 'frames'), 'raw_active': native.stream.get(s, 'active'),
        'input_raw_pending': native.preview.read(s, 0x20068290),
        'source_frames': native.get(s, 'frames'), 'source_blocked': native.get(s, 'blocked'),
        'source_reason': native.get(s, 'reason'), 'source_active': native.get(s, 'active'),
        'video_batches': native.video.get(s, 'batches'), 'video_reason': native.video.get(s, 'reason'),
        'pending_command': native.preview.read(s, 0x20100020),
        'pending_results': native.preview.read(s, 0x2010001c),
        'pending_paired': native.preview.read(s, 0x20380024),
        'core_flags': native.preview.read(s, 0x20102608)}


def check(binary, result):
    build = host.verify_build(binary)
    result['qemu_sha256'] = build['binary_sha256']
    with native.session(binary) as s:
        native.stream.start(s); native.upload(s)
        native.stream.frame(s)
        native.require(native.stream.get(s, 'frames') == 1 and native.preview.get(s, 'batches') == 0,
                       'Fixture did not create one real RAW notification without a running ISP')
        s.write(0x20068290, 0x100)
        native.configure(s)
        result['before'] = snapshot(s)
        native.preview.advance(s)
        result['after'] = snapshot(s)
        result['command'] = s.command
        native.require(result['after']['raw_active'] is False and result['after']['raw_frames'] == 1,
                       'Old RAW source was silently restarted')
        native.require(result['after']['source_frames'] == 1 and result['after']['video_batches'] == 1,
                       'Unconsumed old RAW notification starved the new paired software input')
        result['retired_notifications'] = native.get(s, 'retired-notifications')
        native.require(result['retired_notifications'] == 1, 'Successful replacement did not record its retired notification')
        s.verify_slots(native.packet()[88:], guards=True)
        native.video.pixels(s)
        s.query('system_reset')
        native.require(native.get(s, 'retired-notifications') == 0, 'Reset retained old-notification retirement')
    with native.session(binary) as s:
        native.configure(s); native.upload(s)
        s.write(0x20068008, 0x200)
        native.preview.new_raw(s)
        s.write(0x2006800c, 0x200)
        native.preview.advance(s)
        old = snapshot(s)
        native.require(old['raw_frames'] == 1 and old['source_frames'] == 0 and old['video_batches'] == 1,
                       'An already scheduled legacy transaction was dropped or overwritten')
        native.video.pixels(s)
        native.require(native.get(s, 'retired-notifications') == 0,
                       'Scheduled legacy work was mislabelled as an abandoned notification')
        s.write(0x20068290, 0x100)
        native.video.results.acknowledge(s); native.upload(s, 2); native.preview.advance(s)
        native.require(native.get(s, 'frames') == 1 and native.video.get(s, 'batches') == 2,
                       'Explicit acknowledgement did not release the real output backpressure')
        s.verify_slots(native.packet(2)[88:], guards=True)
        result['scheduled_old_work_and_output_backpressure_preserved'] = True
    with native.session(binary) as s:
        native.stream.start(s); native.upload(s); native.stream.frame(s)
        s.write(0x20068290, 0x100); native.configure(s)
        last = native.preview.read(s, 0x2038031c)
        s.write(0x2038031c, 0x20100000); native.preview.advance(s)
        native.require(native.get(s, 'frames') == 0 and native.get(s, 'retired-notifications') == 0 and
                       native.get(s, 'reason') == 'address', 'Failed DMA preflight retired the old notification')
        for address in native.stream.raw.raw.SLOTS:
            native.require(s.read(address, native.stream.raw.raw.SIZE) == b'\xa5'*native.stream.raw.raw.SIZE,
                           'Failed replacement wrote an earlier source buffer')
        s.write(0x2038031c, last); native.preview.advance(s)
        native.require(native.get(s, 'frames') == 1 and native.get(s, 'retired-notifications') == 1,
                       'The original notification was not retained for the later successful replacement')
        native.video.pixels(s)
        result['failed_replacement_preserves_notification_and_memory'] = True
    return True


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qemu', type=Path, default=host.DEFAULT_QEMU)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError('Handoff evidence is immutable')
    result = {'schema': 1, 'completed': False, 'guest_firmware_executed': False,
              'camera_accessed': False, 'probe_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'native_helper_sha256': hashlib.sha256(Path(native.__file__).read_bytes()).hexdigest()}
    try:
        result['completed'] = check(args.qemu.resolve(), result)
    except Exception as exc:
        result['failure'] = {'type': type(exc).__name__, 'message': str(exc)}
    with args.output.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2)
    print(json.dumps({k: v for k, v in result.items() if k != 'command'}, indent=2), flush=True)
    raise SystemExit(0 if result['completed'] else 1)
