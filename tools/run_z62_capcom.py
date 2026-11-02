# SPDX-License-Identifier: GPL-2.0-or-later
"""Z62 r6 console, with optional functional CAPCOM GPIO acknowledgement.

--firmware or --members selects a candidate; otherwise use pinned original C1.70.
The optional peer models a request/ack wire, not mechanical exposure or capture.
"""
import argparse
import json
from pathlib import Path
import sys

import run_z62_transaction as host
import z62_capcom_device as device
from z62_candidate_firmware import load_candidate
from reference_updates import replace_once

DEFAULT_QEMU = device.WORK / 'runtime/qemu-system-arm.exe'


def verify_build(qemu):
    base = host.verify_build(qemu)
    record = json.loads((qemu.parent.parent / 'capcom-build-manifest.json').read_text(encoding='utf-8'))
    if record.get('schema') != 1 or record.get('version') != device.VERSION:
        raise ValueError('Unsupported CAPCOM manifest')
    if record.get('capcom_device') != device.identity() or record.get('binary_sha256') != base['binary_sha256']:
        raise ValueError('CAPCOM source or binary identity mismatch')
    return record


def configure_command(command, enabled):
    return list(command) + (['-global', 'nikon-z72-boot-config.z62-capcom-sync=on'] if enabled else [])


def apply_status(source):
    path = source / 'tools/z62_console.py'
    text = replace_once(path.read_text(encoding='utf-8'),
        'from tools.z62_transaction_status import transaction_status',
        'from tools.z62_transaction_status import transaction_status\nfrom tools.z62_capcom_status import capcom_status')
    text = replace_once(text, '            state.update(transaction_status(self))',
        '            state.update(transaction_status(self))\n            state.update(capcom_status(self))')
    path.write_text(text, encoding='utf-8', newline='\n')
    (source / 'tools/z62_capcom_status.py').write_bytes(Path(__file__).with_name('z62_capcom_status.py').read_bytes())


def main(argv=None, *, display_version=None, description=None):
    display_version = display_version or device.VERSION
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.add_argument('--capcom-sync', action=argparse.BooleanOptionalAction, default=False)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--firmware', type=Path)
    group.add_argument('--members', type=Path)
    parser.add_argument('--qemu', type=Path, default=DEFAULT_QEMU)
    argv = list(sys.argv[1:] if argv is None else argv)
    if '--help' in argv:
        parser.print_help()
        try:
            host.parse_args(['--help'])
        except SystemExit:
            return
    if '--version' in argv:
        print(device.VERSION)
        return
    args, remaining = parser.parse_known_args(argv)
    qemu = args.qemu.resolve()
    manifest = verify_build(qemu)
    candidate = load_candidate(package=args.firmware, members=args.members) if (args.firmware or args.members) else None
    original_config, original_stage, original_apply = host.configure_command, host.r4.base.stage, host.apply_console
    def stage(*a, **kw):
        work, record = original_stage(*a, **kw)
        record.update(capcom_device=manifest, capcom_sync=args.capcom_sync,
                      requested_host_version=display_version)
        return work, record
    def configure(command, raw=False, completion=False):
        return configure_command(original_config(command, raw, completion), args.capcom_sync)
    def apply(source, persistent=False):
        original_apply(source, persistent)
        apply_status(source)
        if candidate is None:
            path = source / 'tools/z62_console.py'
            path.write_text(replace_once(path.read_text(encoding='utf-8'),
                "PACKAGE_VERSION = '2026.10.28-r5'", "PACKAGE_VERSION = '" + display_version + "'"),
                encoding='utf-8', newline='\n')
            html = source / 'web-z62/index.html'
            text = html.read_text(encoding='utf-8').replace('2026.10.28-r5', display_version)
            text = replace_once(text,
                'r5可选真实RAW DMA完成后的设备事件桥；默认关闭，非硬件时序定论。只读固件状态与事务计数；完整取景、拍照保存和稳定菜单循环尚未验收。',
                description or 'r6增加可选CAPCOM请求/应答GPIO模型。100微秒延迟为功能性假设；不等于机械曝光、取景或拍照完成。完整相机功能仍在开发。')
            html.write_text(text, encoding='utf-8', newline='\n')
    host.configure_command, host.r4.base.stage, host.apply_console = configure, stage, apply
    if '--port' not in remaining and not any(a.startswith('--port=') for a in remaining):
        remaining += ['--port', '8675']
    try:
        print('CAPCOM peer:', args.capcom_sync, '; latency is a functional hypothesis', flush=True)
        host.main(['--qemu', str(qemu)] + remaining, candidate=candidate)
    finally:
        host.configure_command, host.r4.base.stage, host.apply_console = original_config, original_stage, original_apply


if __name__ == '__main__':
    main()
