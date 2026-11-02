"""Experimental r16 host console: frozen r13, absent lens, NOR23 and two-stage input.

The default CMD launcher uses this profile. It retains candidate
firmware identity and unknown-health reporting from the existing host chain.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import run_reference_console as runtime
import run_z62_finite_stats as base
import run_z62_preview as preview
import run_z62_capture_contacts as contacts
import z62_shutter_input_v2 as shutter
import z62_capture_input as input_adapter
import z62_lens_contact as lens
import z62_qmp_transport as monitor
from reference_updates import replace_once

VERSION = '2026.10.29-no-lens-r16'


def verified_hardware_version(qemu):
    """Report a verified descendant's revision instead of the base r13 label."""
    import importlib
    record = contacts.verify_build(qemu)
    for marker, module in (
            ('scene_file_device', 'run_z62_scene_file'),
            ('scene_source_device', 'run_z62_scene_source'),
            ('analog_input_device', 'run_z62_analog_input'),
            ('continuous_statistics_device', 'run_z62_continuous_stats'),
            ('raw_boundary_device', 'run_z62_raw_boundary')):
        if marker in record:
            return importlib.import_module(module).verify_build(qemu)['version']
    return contacts.device.VERSION


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.add_argument('--qemu', type=Path, default=contacts.DEFAULT_QEMU)
    if '--help' in argv:
        parser.print_help()
        return
    if '--version' in argv:
        print(VERSION)
        return
    own, rest = parser.parse_known_args(argv)
    if '--experimental-parameters' not in rest or any(a == '--parameters' or a.startswith('--parameters=') for a in rest):
        raise ValueError('This research profile requires --experimental-parameters; real NOR is not synthesized or replaced')
    hardware_version = verified_hardware_version(own.qemu.resolve())
    original_stage = runtime.stage
    original_configure, original_status, original_main = base.configure_command, base.apply_status, base.base.base.main
    storage_file = None

    def stage(*a, **kw):
        nonlocal storage_file
        work, record = original_stage(*a, **kw)
        data = bytearray(0xE0000)
        data[-4:] = b'ENDM'
        with (work / 'parameters/group23.bin').open('xb') as handle:
            handle.write(data)
        storage_file = work / 'parameters/group23.bin'
        record['parameters']['groups']['group23.bin'] = {
            'size': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
            'address': '0x13420000', 'zero_body': True, 'factory_calibration': False}
        record['input_adapter'] = input_adapter.identity()
        record['lens_contact'] = lens.identity()
        (work / 'session.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
        return work, record

    def configure(command, *a, **kw):
        if storage_file is None:
            raise ValueError('Experimental NOR23 has not been staged')
        result = contacts.configure_command(preview.configure_command(original_configure(command, *a, **kw), True), True)
        # Frozen boot-store ABI accepts three aux files. The separate generic
        # loader restores this fourth read-only experiment at machine reset.
        return result + ['-device', f'loader,file={storage_file},addr=0x13420000,force-raw=on']

    def status(source):
        original_status(source)
        preview.apply_status(source)
        shutter.apply_console(source)
        lens.apply_console(source)
        input_adapter.apply_console(source)
        monitor.apply_console(source)
        path = source / 'tools/z62_console.py'
        content = path.read_text(encoding='utf-8')
        content = replace_once(content, '            state.update(preview_status(self))',
            '            state.update(preview_status(self))\n'
            + '            state["input_adapter"] = ' + repr(input_adapter.identity()) + '\n'
            + '            state["lens_contact"] = ' + repr(lens.identity()) + '\n'
            + '            state["hardware_version"] = ' + repr(hardware_version) + '\n'
            + '            state["host_version"] = ' + repr(VERSION) + '\n'
            + '            state["capture_input"] = self._capture_input_status()\n'
            + '            state["monitor_transport"] = self.qmp.diagnostics()\n'
            + '            state["capture_acceptance"] = {"photo_saved_verified": False, "complete_emulator": False}')
        path.write_text(content, encoding='utf-8', newline='\n')

    def launch(*a, **kw):
        kw.update(display_version=VERSION,
                  description='实验无镜头配置：X半按、S全按（自动包含半按）。使用实验NOR参数和近似取景；照片保存、回放及固件更新安全尚未验收。')
        return original_main(*a, **kw)

    runtime.stage, base.configure_command, base.apply_status, base.base.base.main = stage, configure, status, launch
    if '--port' not in rest and not any(a.startswith('--port=') for a in rest):
        rest += ['--port', '8681']
    try:
        base.main(['--qemu', str(own.qemu)] + rest)
    finally:
        runtime.stage, base.configure_command, base.apply_status, base.base.base.main = original_stage, original_configure, original_status, original_main


if __name__ == '__main__':
    main()
