# SPDX-License-Identifier: GPL-2.0-or-later
"""Z62 r4 development launcher. Original firmware, optional experimental RAW and virtual SD."""
import argparse
import json
from pathlib import Path
import runpy
import subprocess
import sys

import run_reference_console as base
from reference_updates import replace_once
from z62_capture_observation import PRESETS, install_preset
from z62_virtual_sd import CardSession, VERSION, digest, image_path

DEFAULT_QEMU = base.ROOT / '.build' / f'z62-functional-{VERSION}' / 'runtime/qemu-system-arm.exe'


def apply_console(source, persistent=False):
    """Modify only the staged host console, never firmware or pinned donors."""
    path = source / 'tools/z62_console.py'
    text = path.read_text(encoding='utf-8')
    if persistent:
        text = replace_once(text, 'format=raw,snapshot=on', 'format=raw,snapshot=off')
    text = replace_once(text, "PACKAGE_VERSION = '2026.10.27-r1'", f"PACKAGE_VERSION = '{VERSION}'")
    text = replace_once(text, 'from tools.z62_reference_features import configure_command, diagnostics',
                        'from tools.z62_reference_features import configure_command, diagnostics\n'
                        'from tools.z62_development_status import firmware_health, functional_raw_status')
    text = replace_once(text, '            state.update(diagnostics(self))',
                        '            state.update(diagnostics(self))\n'
                        '            state.update(firmware_health(self))\n'
                        '            state.update(functional_raw_status(self))')
    shared = source / 'tools/web_console.py'
    shared_text = replace_once(shared.read_text(encoding='utf-8'),
        '        if self.process is not None and self.process.poll() is None:\n'
        '            self.process.terminate()',
        '        if self.process is not None and self.process.poll() is None and self.qmp is not None:\n'
        '            try:\n'
        '                self.qmp.command("quit")\n'
        '                self.process.wait(timeout=10)\n'
        '            except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired):\n'
        '                pass\n'
        '        if self.process is not None and self.process.poll() is None:\n'
        '            self.process.terminate()')
    js = source / 'web-z62/console.js'
    js_text = replace_once(js.read_text(encoding='utf-8'),
        "    $('connection').textContent = state.error ? '运行异常'",
        "    const firmwareWarning = state.firmware_health_known === false ? '固件状态未知' : "
        "state.firmware_status_codes?.length ? '固件状态: ' + state.firmware_status_codes.map(c => '0x' + c.toString(16)).join(', ') : null;\n"
        "    $('connection').textContent = firmwareWarning || (state.error ? '运行异常'")
    js_text = replace_once(js_text, " : '启动中';", " : '启动中');")
    js_text = replace_once(js_text, '    if (state.error) notice(state.error);',
                          "    if (firmwareWarning) notice(firmwareWarning + '；这不是正常取景画面。');\n"
                          '    else if (state.error) notice(state.error);')
    html = source / 'web-z62/index.html'
    html_text = replace_once(html.read_text(encoding='utf-8'), '当前可用范围 · R2', '开发版 · ' + VERSION)
    html_text = replace_once(html_text,
        '普通入口用于操作原厂菜单。“启动主屏实验”入口回放两次实验输入，可显示拍摄主屏；仍可能提示存储卡错误，绿色背景不是真实取景。尚不支持正常拍照。',
        '原固件菜单与状态读取；可选虚拟SD快照或持久保存。合成RAW为显式实验，像素打包和完整取景链未验收；菜单循环仍可能报错，不支持正常拍照录像。')
    html_text = replace_once(html_text, '本地实验版 · 2026-10-25', '独立开发版 · ' + VERSION)
    js_text = replace_once(js_text, '实时画面 · 1024 × 682', '固件LCD输出 · 非真实取景')
    # Validate all anchors before changing this disposable host tree.
    path.write_text(text, encoding='utf-8', newline='\n')
    shared.write_text(shared_text, encoding='utf-8', newline='\n')
    js.write_text(js_text, encoding='utf-8', newline='\n')
    html.write_text(html_text, encoding='utf-8', newline='\n')
    (source / 'tools/z62_development_status.py').write_bytes(
        Path(__file__).with_name('z62_development_status.py').read_bytes())


def configure_command(command, raw=False):
    result = list(command)
    if raw:
        result += ['-global', 'nikon-z72-input-config.functional-raw=on']
    return result


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', action='version', version=VERSION)
    parser.add_argument('--qemu', type=Path, default=DEFAULT_QEMU)
    parser.add_argument('--port', type=int, default=8672)
    parameters = parser.add_mutually_exclusive_group(required=True)
    parameters.add_argument('--parameters', type=Path)
    parameters.add_argument('--experimental-parameters', action='store_true')
    parser.add_argument('--capture-preset', choices=PRESETS, default='baseline')
    parser.add_argument('--functional-raw', action='store_true',
                        help='Experimental descriptor-bounded packed12 DMA; NOT verified live view or packing')
    parser.add_argument('--sd-card', type=Path)
    parser.add_argument('--sd-mode', choices=('snapshot', 'persistent'), default='snapshot')
    parser.add_argument('--no-auto-menu', action='store_true')
    parser.add_argument('--input-trace', action='store_true')
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error('Port must be 1..65535')
    if args.sd_mode == 'persistent' and args.sd_card is None:
        parser.error('--sd-mode persistent requires --sd-card')
    if args.sd_card:
        try:
            args.sd_card = image_path(args.sd_card)
        except (OSError, ValueError) as exc:
            parser.error(str(exc))
    return args


def verify_functional_build(qemu, required=False):
    manifest = qemu.parent.parent / 'functional-build-manifest.json'
    if not manifest.is_file():
        if required:
            raise ValueError('--functional-raw requires a verified functional device build')
        return None
    import z62_functional_device
    record = json.loads(manifest.read_text(encoding='utf-8'))
    if record.get('schema') != 1 or record.get('version') != VERSION:
        raise ValueError('Unsupported functional build manifest')
    if record.get('functional_device') != z62_functional_device.identity():
        raise ValueError('Functional device source identity mismatch; rebuild before running')
    if record.get('binary_sha256') != digest(qemu):
        raise ValueError('Functional device binary hash mismatch')
    return record


def main(argv=None):
    args = parse_args(argv)
    qemu = args.qemu.resolve()
    device_record = verify_functional_build(qemu, args.functional_raw)
    work, record = base.stage('z62', qemu, args.parameters, args.experimental_parameters, True)
    card = None
    processes = []
    original_popen = subprocess.Popen
    old_path, old_argv = list(sys.path), list(sys.argv)
    completed = False
    record.update(host_version=VERSION, functional_device=device_record,
                  functional_raw=args.functional_raw, capture_preset=args.capture_preset,
                  capture_properties=list(PRESETS[args.capture_preset]),
                  live_view_verified=False, sd_card=None)
    try:
        if args.sd_card:
            card = CardSession(args.sd_card, work, args.sd_mode)
            record['sd_card'] = card.record()
        apply_console(work / 'source', args.sd_mode == 'persistent')
        (work / 'session.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
        script = work / 'source/tools/z62_console.py'
        sys.path.insert(0, str(work / 'source'))
        sys.argv = [str(script), '--qemu', str(qemu), '--port', str(args.port),
                    '--master', str(work / 'inputs/master.bin'), '--slave', str(work / 'inputs/slave.bin'),
                    '--controller', str(work / 'inputs/controller.bin'),
                    '--parameters', str(work / 'parameters'), '--runs', str(work / 'runs')]
        if card:
            sys.argv += ['--sd-card', str(card.staged)]
        if args.no_auto_menu:
            sys.argv.append('--no-auto-menu')
        if args.input_trace:
            sys.argv.append('--input-trace')
        base.install_native_process_adapter(work)
        parent = install_preset(subprocess.Popen, args.capture_preset)
        class DevelopmentPopen(parent):
            def __init__(self, command, *a, **kw):
                is_qemu = isinstance(command, (list, tuple)) and 'qemu-system-arm' in str(command[0])
                if is_qemu:
                    command = configure_command(command, args.functional_raw)
                super().__init__(command, *a, **kw)
                if is_qemu:
                    processes.append(self)
        subprocess.Popen = DevelopmentPopen
        print(f'Z62 development {VERSION}: http://127.0.0.1:{args.port}', flush=True)
        print('Session: ' + str(work), flush=True)
        print('Original firmware; experimental model, no physical camera access. Live view is NOT accepted.', flush=True)
        if card:
            print('SD: ' + args.sd_mode + '; persistent save only after a clean QEMU exit.', flush=True)
        runpy.run_path(str(script), run_name='__main__')
        completed = bool(processes) and all(p.poll() == 0 for p in processes)
        if card and args.sd_mode == 'persistent':
            if not completed:
                raise RuntimeError('QEMU did not exit cleanly; SD source unchanged, recovery: ' + str(card.staged))
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
