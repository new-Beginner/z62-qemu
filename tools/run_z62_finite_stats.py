"""r8 finite-statistics research entry; complete camera emulation is not claimed."""
import argparse
import json
from pathlib import Path
import sys

import run_z62_raw_stream as base
import z62_finite_stats_device as device
from reference_updates import replace_once

DEFAULT_QEMU = device.WORK/'runtime/qemu-system-arm.exe'


def verify_build(qemu):
    prior = base.verify_build(qemu)
    record = json.loads((qemu.parent.parent/'finite-stats-build-manifest.json').read_text(encoding='utf-8'))
    if record.get('schema') != 1 or record.get('version') != device.VERSION:
        raise ValueError('Unsupported finite stats manifest')
    if record.get('finite_stats_device') != device.identity() or record.get('binary_sha256') != prior['binary_sha256']:
        raise ValueError('Finite stats source or binary identity mismatch')
    return record


def configure_command(command, enabled=True):
    result = list(command)
    for prop in ('nikon-z72-boot-config.z62-finite-stats', 'nikon-z72-input-config.functional-finite-stats'):
        argument = prop+'=on'
        if enabled and argument not in result:
            result += ['-global', argument]
    return result


def apply_status(source):
    path = source/'tools/z62_console.py'
    text = replace_once(path.read_text(encoding='utf-8'),
        'from tools.z62_raw_stream_status import raw_stream_status',
        'from tools.z62_raw_stream_status import raw_stream_status\nfrom tools.z62_finite_stats_status import finite_stats_status')
    text = replace_once(text, '            state.update(raw_stream_status(self))',
        '            state.update(raw_stream_status(self))\n            state.update(finite_stats_status(self))')
    path.write_text(text, encoding='utf-8', newline='\n')
    (source/'tools/z62_finite_stats_status.py').write_bytes(Path(__file__).with_name('z62_finite_stats_status.py').read_bytes())


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    p = argparse.ArgumentParser(description=__doc__, add_help=False)
    p.add_argument('--finite-stats', action=argparse.BooleanOptionalAction, default=True)
    p.add_argument('--qemu', type=Path, default=DEFAULT_QEMU)
    if '--help' in argv:
        p.print_help(); return
    if '--version' in argv:
        print(device.VERSION); return
    own, rest = p.parse_known_args(argv)
    verify_build(own.qemu.resolve())
    original_config, original_status, original_main = base.configure_command, base.apply_status, base.base.main
    def configure(command, *a, **kw):
        return configure_command(original_config(command, *a, **kw), own.finite_stats)
    def status(source):
        original_status(source)
        apply_status(source)
    def launch(*a, **kw):
        kw.update(display_version=device.VERSION,
            description='r8有限统计采集实验：真实RAW数据经区域均值计算后逐帧写入；61槽全部完成才报告批次。统计算法为功能近似，完整取景与拍照尚未验收。')
        return original_main(*a, **kw)
    base.configure_command, base.apply_status, base.base.main = configure, status, launch
    if '--port' not in rest and not any(a.startswith('--port=') for a in rest):
        rest += ['--port', '8678']
    for flag in ('--input-drain', '--paired-sync'):
        if flag not in rest: rest.append(flag)
    try:
        base.main(['--qemu', str(own.qemu)] + rest)
    finally:
        base.configure_command, base.apply_status, base.base.main = original_config, original_status, original_main


if __name__ == '__main__':
    main()
