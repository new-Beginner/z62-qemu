"""Independent r9 approximate-preview research entry; original r8 remains available."""
import argparse
import json
from pathlib import Path
import sys
import run_z62_finite_stats as base
import z62_preview_device as device
from reference_updates import replace_once

DEFAULT_QEMU=device.WORK/'runtime/qemu-system-arm.exe'


def verify_build(qemu):
    prior=base.verify_build(qemu)
    record=json.loads((qemu.parent.parent/'preview-build-manifest.json').read_text(encoding='utf-8'))
    if record.get('schema')!=1 or record.get('version')!=device.VERSION:
        raise ValueError('Unsupported preview manifest')
    if record.get('preview_device')!=device.identity() or record.get('binary_sha256')!=prior['binary_sha256']:
        raise ValueError('Preview source or binary identity mismatch')
    return record


def configure_command(command,enabled=True):
    result=list(command)
    value='nikon-z72-boot-config.z62-preview=on'
    if enabled and value not in result: result+=['-global',value]
    return result


def apply_status(source):
    path=source/'tools/z62_console.py'
    text=replace_once(path.read_text(encoding='utf-8'),
        'from tools.z62_finite_stats_status import finite_stats_status',
        'from tools.z62_finite_stats_status import finite_stats_status\nfrom tools.z62_preview_status import preview_status')
    text=replace_once(text,'            state.update(finite_stats_status(self))',
        '            state.update(finite_stats_status(self))\n            state.update(preview_status(self))')
    path.write_text(text,encoding='utf-8',newline='\n')
    (source/'tools/z62_preview_status.py').write_bytes(Path(__file__).with_name('z62_preview_status.py').read_bytes())


def main(argv=None):
    argv=list(sys.argv[1:] if argv is None else argv)
    p=argparse.ArgumentParser(description=__doc__,add_help=False)
    p.add_argument('--preview',action=argparse.BooleanOptionalAction,default=True)
    p.add_argument('--qemu',type=Path,default=DEFAULT_QEMU)
    if '--help' in argv: p.print_help();return
    if '--version' in argv: print(device.VERSION);return
    own,rest=p.parse_known_args(argv)
    verify_build(own.qemu.resolve())
    original_config,original_status,original_main=base.configure_command,base.apply_status,base.base.base.main
    def configure(command,*a,**kw): return configure_command(original_config(command,*a,**kw),own.preview)
    def status(source): original_status(source);apply_status(source)
    def launch(*a,**kw):
        kw.update(display_version=device.VERSION,
            description='r9功能近似预览：实际RAW经裁边、CFA单元颜色和NV12变换后写入原厂输出描述符。统计bank0和任意处理节点未实现，画质、拍照保存与刷写安全未验收。')
        return original_main(*a,**kw)
    base.configure_command,base.apply_status,base.base.base.main=configure,status,launch
    if '--port' not in rest and not any(a.startswith('--port=') for a in rest): rest+=['--port','8679']
    try: base.main(['--qemu',str(own.qemu)]+rest)
    finally: base.configure_command,base.apply_status,base.base.base.main=original_config,original_status,original_main


if __name__=='__main__': main()
