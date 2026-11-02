# SPDX-License-Identifier: GPL-2.0-or-later
"""Opt-in Z62 reference updates. Mutate generated copies only, never donors.

Sources: JKWTCN/z72-qemu a64640d, 781ef35, 6a8d5f4, 97ec64c.
This adds a register contract and diagnostics, not physical LCD glass/sensor data.
"""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
VERSION = '2026.10.27-r1'
UPSTREAM = '4a7bed36b6e747f58d5ab25f31b06a31fa7c6ec2'
FILES = {
    'nikon-z72-controller-panel.c': '7d7c1e9de14e084f8c52866003be2de80e0de0f2f5bf56d2c2cbab76da525a2f',
    'nikon-z72-controller-i2c.c': '41ae3fe79c875a49a8bceea5500d9e1210067ae38b6115217ee96c8533696e23',
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Unexpected reference source anchor: ' + old[:90])
    return text.replace(old, new, 1)


def upstream_files():
    result = {}
    repo = ROOT / 'third_party/z72-qemu'
    for name, digest in FILES.items():
        data = subprocess.check_output(['git', '-C', str(repo), 'show', f'{UPSTREAM}:qemu/{name}'])
        if sha(data) != digest:
            raise ValueError('Upstream source hash mismatch: ' + name)
        result[name] = data
    return result


def identity():
    return {'version': VERSION, 'upstream_commit': UPSTREAM,
            'upstream_source_sha256': FILES,
            'adapter_sha256': sha(Path(__file__).read_bytes()),
            'trace_header_sha256': sha((ROOT / 'qemu/reference-updates/nikon-z62-input-trace.h').read_bytes()),
            'console_features_sha256': sha((ROOT / 'tools/z62_reference_features.py').read_bytes()),
            'guest_patched': False, 'physical_panel_segments': False,
            'trace_changes': 'short-ring origin fixed; uint64 count; clear on reset; VMState 38 only'}


def apply_source(source):
    """Called after the baseline donor has been prepared and verified."""
    arm = source / 'hw/arm'
    upstream = upstream_files()
    i2c = arm / 'nikon-z72-controller-i2c.c'
    if sha(i2c.read_bytes()) != '0cf66c7829feeb9da1c230b3e66efb32a7609e1377fd0944c5e86b2bee718bb2':
        raise ValueError('Unexpected baseline controller I2C')
    board = arm / 'nikon-z72.c'
    text = board.read_text(encoding='utf-8')
    text = replace_once(text, '    uint32_t sample_lines;\n', '''    uint32_t sample_lines;
    bool input_trace;
    uint64_t input_trace_count;
    uint32_t input_trace_addresses[256];
    uint32_t input_trace_values[256];
    uint8_t input_trace_writes[256];
''')
    text = replace_once(text, 'static uint64_t boot_config_read(',
                        '#include "nikon-z62-input-trace.h"\n\nstatic uint64_t boot_config_read(')
    text = replace_once(text, '        s->frame_count++;\n    }\n    return value;',
                        '        s->frame_count++;\n    }\n'
                        '    boot_config_trace(s, boot_config_addresses[word->index], value, false);\n'
                        '    return value;')
    text = replace_once(text, '    uint32_t *stored = &s->values[word->index];\n',
                        '    uint32_t *stored = &s->values[word->index];\n'
                        '    boot_config_trace(s, address, (uint32_t)value, true);\n')
    text = replace_once(text, '    s->frame_sync_count = 0;\n',
                        '    s->frame_sync_count = 0;\n    s->input_trace_count = 0;\n')
    text = replace_once(text, '    .version_id = 37,\n    .minimum_version_id = 37,',
                        '    .version_id = 38,\n    .minimum_version_id = 38,')
    text = replace_once(text, '        VMSTATE_UINT8_V(controller_levels, NikonZ72BootConfig, 25),', '''        VMSTATE_BOOL(input_trace, NikonZ72BootConfig),
        VMSTATE_UINT64(input_trace_count, NikonZ72BootConfig),
        VMSTATE_UINT32_ARRAY(input_trace_addresses, NikonZ72BootConfig, 256),
        VMSTATE_UINT32_ARRAY(input_trace_values, NikonZ72BootConfig, 256),
        VMSTATE_UINT8_ARRAY(input_trace_writes, NikonZ72BootConfig, 256),
        VMSTATE_UINT8_V(controller_levels, NikonZ72BootConfig, 25),''')
    text = replace_once(text, '    qdev_init_gpio_in(DEVICE(obj), peer_ready_input, 1);', '''    object_property_add_uint64_ptr(obj, "input-trace-count", &s->input_trace_count,
                                   OBJ_PROP_FLAG_READ);
    object_property_add_str(obj, "input-trace-log", boot_config_input_trace_get, NULL);
    qdev_init_gpio_in(DEVICE(obj), peer_ready_input, 1);''')
    text = replace_once(text, '        DEFINE_PROP_BOOL("sensor-sample", NikonZ72BootConfig, sensor_sample, false),',
                        '        DEFINE_PROP_BOOL("input-trace", NikonZ72BootConfig, input_trace, false),\n'
                        '        DEFINE_PROP_BOOL("sensor-sample", NikonZ72BootConfig, sensor_sample, false),')
    meson = arm / 'meson.build'
    if 'nikon-z72-controller-panel.c' in meson.read_text():
        raise ValueError('Reference updates already applied')
    # Compute/validate every edit before writing the generated tree.
    header = (ROOT / 'qemu/reference-updates/nikon-z62-input-trace.h').read_bytes()
    board.write_text(text, encoding='utf-8', newline='\n')
    for name, data in upstream.items():
        (arm / name).write_bytes(data)
    (arm / 'nikon-z62-input-trace.h').write_bytes(header)
    with meson.open('a', encoding='utf-8') as stream:
        stream.write("\narm_ss.add(when: 'CONFIG_NIKON_Z72_LAB', if_true: files('nikon-z72-controller-panel.c'))\n")
    return identity()


def apply_console(source):
    """Only staged Python host code; no guest state or instruction changes."""
    path = source / 'tools/z62_console.py'
    text = path.read_text(encoding='utf-8')
    text = replace_once(text, "PACKAGE_VERSION = '2026-10-26-r3'",
                        f"PACKAGE_VERSION = '{VERSION}'\n"
                        'from tools.z62_reference_features import configure_command, diagnostics')
    text = replace_once(text, '        for device in devices:\n',
                        '        command = configure_command(command, args)\n        for device in devices:\n')
    text = replace_once(text, '        return state\n\n    def _cleanup(self):',
                        '            state.update(diagnostics(self))\n        return state\n\n    def _cleanup(self):')
    text = replace_once(text, "    parser.add_argument('--no-auto-menu', action='store_true')", '''    parser.add_argument('--no-auto-menu', action='store_true')
    parser.add_argument('--sampling-source', action='store_true',
                        help='Experimental 30 Hz sample-ready source, not sensor pixels')
    parser.add_argument('--input-trace', action='store_true', help='Read-only input MMIO ring')''')
    probe = source / 'tools/z62_probe.py'
    ptext = replace_once(probe.read_text(encoding='utf-8'),
                        "'nikon-z72-controller-register-bank,bus=controller-i2c0,address=13,'",
                        "'nikon-z72-controller-panel,bus=controller-i2c0,address=13,id=shoulder,'")
    path.write_text(text, encoding='utf-8', newline='\n')
    probe.write_text(ptext, encoding='utf-8', newline='\n')
    (source / 'tools/z62_reference_features.py').write_bytes(
        (ROOT / 'tools/z62_reference_features.py').read_bytes())


def verify_binary(binary):
    manifest = binary.parent.parent / 'reference-build-manifest.json'
    data = json.loads(manifest.read_text(encoding='utf-8'))
    if (data.get('reference_updates') != identity() or data.get('profile') != 'z62' or
            data.get('binary_sha256') != sha(binary.read_bytes())):
        raise ValueError('Updated reference binary/manifest does not match this adapter')
