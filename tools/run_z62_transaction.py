# SPDX-License-Identifier: GPL-2.0-or-later
"""Independent Z62 r5 host. Transaction-linked completion is experimental and opt-in."""
import argparse
import json
from pathlib import Path
import runpy
import subprocess
import sys

import run_z62_development as r4
from reference_updates import replace_once
from z62_capture_observation import PRESETS, install_preset
from z62_virtual_sd import CardSession, digest, image_path

VERSION = '2026.10.28-r5'
ROOT = r4.base.ROOT
DEFAULT_QEMU = ROOT / '.build' / ('z62-transaction-' + VERSION) / 'runtime/qemu-system-arm.exe'


def configure_command(command, raw=False, completion=False):
    if completion and not raw:
        raise ValueError('RAW completion requires real functional RAW DMA')
    result = r4.configure_command(command, raw)
    if completion:
        result += ['-global', 'nikon-z62-sensor-config.functional-raw-completion=on']
    return result


def verify_build(qemu):
    import z62_transaction_device
    record = json.loads((qemu.parent.parent / 'transaction-build-manifest.json').read_text(encoding='utf-8'))
    if record.get('schema') != 1 or record.get('version') != VERSION:
        raise ValueError('Unsupported transaction build manifest')
    if record.get('transaction_device') != z62_transaction_device.identity():
        raise ValueError('Transaction device identity mismatch')
    if record.get('binary_sha256') != digest(qemu):
        raise ValueError('Transaction binary hash mismatch')
    raw = r4.verify_functional_build(qemu, True)
    if record['binary_sha256'] != raw['binary_sha256']:
        raise ValueError('RAW and transaction manifests describe different binaries')
    return record


def apply_console(source, persistent=False):
    r4.apply_console(source, persistent)
    path = source / 'tools/z62_console.py'
    text = replace_once(path.read_text(encoding='utf-8'),
                        f"PACKAGE_VERSION = '{r4.VERSION}'", f"PACKAGE_VERSION = '{VERSION}'")
    text = replace_once(text,
        'from tools.z62_development_status import firmware_health, functional_raw_status',
        'from tools.z62_development_status import firmware_health, functional_raw_status\n'
        'from tools.z62_transaction_status import transaction_status')
    text = replace_once(text, '            state.update(functional_raw_status(self))',
                        '            state.update(functional_raw_status(self))\n'
                        '            state.update(transaction_status(self))')
    html = source / 'web-z62/index.html'
    content = html.read_text(encoding='utf-8')
    content = replace_once(content, '独立开发版 · ' + r4.VERSION, '独立开发版 · ' + VERSION)
    content = replace_once(content, '开发版 · ' + r4.VERSION, '开发版 · ' + VERSION)
    content = replace_once(content,
        '原固件菜单与状态读取；可选虚拟SD快照或持久保存。合成RAW为显式实验，像素打包和完整取景链未验收；菜单循环仍可能报错，不支持正常拍照录像。',
        'r5可选真实RAW DMA完成后的设备事件桥；默认关闭，非硬件时序定论。只读固件状态与事务计数；完整取景、拍照保存和稳定菜单循环尚未验收。')
    path.write_text(text, encoding='utf-8', newline='\n')
    html.write_text(content, encoding='utf-8', newline='\n')
    (source / 'tools/z62_transaction_status.py').write_bytes(
        Path(__file__).with_name('z62_transaction_status.py').read_bytes())


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--version', action='version', version=VERSION)
    p.add_argument('--qemu', type=Path, default=DEFAULT_QEMU)
    p.add_argument('--port', type=int, default=8673)
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument('--parameters', type=Path)
    group.add_argument('--experimental-parameters', action='store_true')
    p.add_argument('--capture-preset', choices=PRESETS, default='baseline')
    p.add_argument('--functional-raw', action='store_true')
    p.add_argument('--raw-completion', action='store_true',
                   help='Explicit experimental actual-DMA -> mode2 sensor event; no ISP/live-view claim')
    p.add_argument('--sd-card', type=Path)
    p.add_argument('--sd-mode', choices=('snapshot', 'persistent'), default='snapshot')
    p.add_argument('--no-auto-menu', action='store_true')
    p.add_argument('--input-trace', action='store_true')
    args = p.parse_args(argv)
    if not 1 <= args.port <= 65535:
        p.error('Port must be 1..65535')
    if args.raw_completion and not args.functional_raw:
        p.error('--raw-completion requires --functional-raw')
    if args.sd_mode == 'persistent' and args.sd_card is None:
        p.error('Persistent mode requires --sd-card')
    if args.sd_card:
        try:
            args.sd_card = image_path(args.sd_card)
        except (OSError, ValueError) as exc:
            p.error(str(exc))
    return args


def main(argv=None, *, candidate=None):
    args = parse_args(argv)
    qemu = args.qemu.resolve()
    device = verify_build(qemu)
    work, record = r4.base.stage('z62', qemu, args.parameters, args.experimental_parameters, True)
    original_popen = subprocess.Popen
    old_path, old_argv = list(sys.path), list(sys.argv)
    processes, card, completed = [], None, False
    record.update(host_version=record.get('requested_host_version', VERSION), transaction_device=device,
                  functional_raw=args.functional_raw, raw_completion=args.raw_completion,
                  capture_preset=args.capture_preset, capture_properties=list(PRESETS[args.capture_preset]),
                  live_view_verified=False, sd_card=None)
    try:
        if args.sd_card:
            card = CardSession(args.sd_card, work, args.sd_mode)
            record['sd_card'] = card.record()
        apply_console(work / 'source', args.sd_mode == 'persistent')
        if candidate is not None:
            from z62_candidate_firmware import install_candidate, apply_console as apply_candidate
            install_candidate(work, record, candidate)
            apply_candidate(work / 'source', candidate)
            record['host_version'] = '2026.10.28-candidate1'
        (work / 'session.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
        script = work / 'source/tools/z62_console.py'
        sys.path.insert(0, str(work / 'source'))
        sys.argv = [str(script), '--qemu', str(qemu), '--port', str(args.port),
                    '--master', str(work / 'inputs/master.bin'), '--slave', str(work / 'inputs/slave.bin'),
                    '--controller', str(work / 'inputs/controller.bin'),
                    '--parameters', str(work / 'parameters'), '--runs', str(work / 'runs')]
        if card:
            sys.argv += ['--sd-card', str(card.staged)]
        if args.no_auto_menu or candidate is not None:
            sys.argv.append('--no-auto-menu')
        if args.input_trace:
            sys.argv.append('--input-trace')
        r4.base.install_native_process_adapter(work)
        parent = install_preset(subprocess.Popen, args.capture_preset)
        class TransactionPopen(parent):
            def __init__(self, command, *a, **kw):
                is_qemu = isinstance(command, (list, tuple)) and 'qemu-system-arm' in str(command[0])
                if is_qemu:
                    command = configure_command(command, args.functional_raw, args.raw_completion)
                super().__init__(command, *a, **kw)
                if is_qemu:
                    processes.append(self)
        subprocess.Popen = TransactionPopen
        label = 'transaction ' + record['host_version'] if candidate is None else 'candidate 2026.10.28-candidate1'
        print(f'Z62 {label}: http://127.0.0.1:{args.port}', flush=True)
        print('Session: ' + str(work), flush=True)
        print(f'RAW={args.functional_raw}, completion={args.raw_completion}, preset={args.capture_preset}', flush=True)
        print(('Original firmware' if candidate is None else 'User-selected candidate; health UNKNOWN') +
              '; no physical camera. Transaction hypothesis, NOT verified live view.', flush=True)
        runpy.run_path(str(script), run_name='__main__')
        completed = bool(processes) and all(process.poll() == 0 for process in processes)
        if card and args.sd_mode == 'persistent':
            if not completed:
                raise RuntimeError('Abnormal QEMU exit; source unchanged; recovery: ' + str(card.staged))
            card.commit()
    finally:
        subprocess.Popen = original_popen
        sys.path[:], sys.argv = old_path, old_argv
        record['clean_exit'] = completed
        if card:
            record['sd_card'] = card.record()
            card.close()
        (work / 'session.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
