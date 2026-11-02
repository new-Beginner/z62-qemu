# SPDX-License-Identifier: GPL-2.0-or-later
"""Independent r7 native frame-driven RAW experiment, not an ISP/live-view release."""
import argparse
import json
from pathlib import Path
import sys

import run_z62_capcom as base
import z62_raw_stream_device as device
from reference_updates import replace_once

DEFAULT_QEMU = device.WORK/'runtime/qemu-system-arm.exe'


def verify_build(qemu):
    prior = base.verify_build(qemu)
    manifest = json.loads((qemu.parent.parent/'raw-stream-build-manifest.json').read_text(encoding='utf-8'))
    if manifest.get('schema') != 1 or manifest.get('version') != device.VERSION:
        raise ValueError('Unsupported RAW stream manifest')
    if manifest.get('raw_stream_device') != device.identity() or manifest.get('binary_sha256') != prior['binary_sha256']:
        raise ValueError('RAW stream source or binary identity mismatch')
    return manifest


def configure_command(command, enabled=True, *, drain=False, paired=False):
    result = list(command)
    for active, prop in ((enabled, 'z62-raw-stream'), (drain, 'input-command-completion'),
                         (paired, 'frame-start')):
        argument = 'nikon-z72-boot-config.'+prop+'=on'
        if active and argument not in result:
            result += ['-global', argument]
    return result


def apply_status(source):
    path = source/'tools/z62_console.py'
    text = replace_once(path.read_text(encoding='utf-8'),
        'from tools.z62_capcom_status import capcom_status',
        'from tools.z62_capcom_status import capcom_status\nfrom tools.z62_raw_stream_status import raw_stream_status')
    text = replace_once(text, '            state.update(capcom_status(self))',
        '            state.update(capcom_status(self))\n            state.update(raw_stream_status(self))')
    path.write_text(text, encoding='utf-8', newline='\n')
    (source/'tools/z62_raw_stream_status.py').write_bytes(Path(__file__).with_name('z62_raw_stream_status.py').read_bytes())


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, add_help=False)
    p.add_argument('--raw-stream', action=argparse.BooleanOptionalAction, default=True)
    p.add_argument('--qemu', type=Path, default=DEFAULT_QEMU)
    p.add_argument('--input-drain', action='store_true')
    p.add_argument('--paired-sync', action='store_true')
    argv = list(sys.argv[1:] if argv is None else argv)
    if '--help' in argv:
        p.print_help()
        base.main(['--help'])
        return
    if '--version' in argv:
        print(device.VERSION)
        return
    own, rest = p.parse_known_args(argv)
    manifest = verify_build(own.qemu.resolve())
    if own.raw_stream and '--functional-raw' not in rest:
        rest += ['--functional-raw']
    original_config, original_status, original_stage = base.configure_command, base.apply_status, base.host.r4.base.stage
    def configure(command, enabled):
        return configure_command(original_config(command, enabled), own.raw_stream,
                                 drain=own.input_drain, paired=own.paired_sync)
    def status(source):
        original_status(source)
        apply_status(source)
    def stage(*a, **kw):
        work, record = original_stage(*a, **kw)
        record.update(raw_stream_device=manifest, raw_stream=own.raw_stream,
                      input_drain_completion=own.input_drain, frame_start_phase=own.paired_sync)
        return work, record
    base.configure_command, base.apply_status, base.host.r4.base.stage = configure, status, stage
    if '--port' not in rest and not any(a.startswith('--port=') for a in rest):
        rest += ['--port', '8677']
    try:
        print('r7 native RAW stream:', own.raw_stream, '; ISP and live view remain unverified', flush=True)
        base.main(['--qemu', str(own.qemu)] + rest, display_version=device.VERSION,
                  description='r7增加自动RAW帧源：实际写入成功后由设备报告通道2完成。仍未实现完整ISP、连续取景和拍照保存，不是刷机安全验证。')
    finally:
        base.configure_command, base.apply_status, base.host.r4.base.stage = original_config, original_status, original_stage


if __name__ == '__main__':
    main()
