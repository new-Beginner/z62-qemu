# SPDX-License-Identifier: GPL-2.0-or-later
"""Independent r6 CAPCOM GPIO peer adapter; consumes exact r5 board source."""
from pathlib import Path
import reference_updates as reference

ROOT = Path(__file__).resolve().parents[1]
VERSION = '2026.10.28-r6'
WORK = ROOT / '.build' / ('z62-capcom-' + VERSION)
HEADER = ROOT / 'qemu/z62-capcom/nikon-z62-capcom.h'
INPUT_SHA = 'e02a627bf37a16f92e9313a7f0a55a0a011fb218a24fc41b2830eba47973e691'


def identity():
    return {'schema': 1, 'version': VERSION, 'input_sha256': INPUT_SHA,
            'adapter_sha256': reference.sha(Path(__file__).read_bytes()),
            'header_sha256': reference.sha(HEADER.read_bytes()),
            'default_enabled': False, 'latency_ns_hypothesis': 100000,
            'request': '0x04282018 bit8', 'acknowledge': '0x04282014 bit7 IRQ65',
            'guest_software_patched': False, 'mechanical_capture_verified': False}


def render(data):
    if reference.sha(data) != INPUT_SHA:
        raise ValueError('CAPCOM base board SHA mismatch')
    text = data.decode('utf-8')
    replace = reference.replace_once
    text = replace(text, '    bool controller_ack_output;', '''    bool controller_ack_output;
    bool z62_capcom_sync, capcom_request, capcom_ack, capcom_pending;
    uint64_t capcom_requests, capcom_completions, capcom_coalesced;
    QEMUTimer *capcom_timer;''')
    text = replace(text, 'static void controller_update_irqs(NikonZ72BootConfig *s)\n{',
        '#include "nikon-z62-capcom.h"\n\n'
        'static void controller_update_irqs(NikonZ72BootConfig *s)\n{\n    capcom_update_irq(s);')
    text = replace(text, '    if (s->peer_connected &&\n        boot_config_addresses[word->index] == peer_ready_address(s)) {',
        '''    if (capcom_active(s)) {
        hwaddr address = boot_config_addresses[word->index];
        if (address == 0x04282014) {
            value = (value & ~0x80u) | (s->capcom_ack ? 0x80u : 0);
        } else if (address == 0x04282018) {
            value = (value & ~0x100u) | (s->capcom_request ? 0x100u : 0);
        }
    }
    if (s->peer_connected &&
        boot_config_addresses[word->index] == peer_ready_address(s)) {''')
    text = replace(text, '    if (s->controller_connected) {\n        if (address == 0x04282018',
        '''    capcom_write(s, address, value);
    if (capcom_active(s) && address == 0x0426f008) {
        uint32_t preserved = s->controller_connected ? 0xdu : 1u;
        *stored = (value & ~preserved) | (*stored & preserved);
        return;
    }
    if (s->controller_connected) {
        if (address == 0x04282018''')
    text = replace(text, '    memset(s->values, 0, sizeof(s->values));',
        '    memset(s->values, 0, sizeof(s->values));\n    capcom_reset(s);')
    text = replace(text, '    .version_id = 38,\n    .minimum_version_id = 38,',
        '    .version_id = 39,\n    .minimum_version_id = 39,')
    text = replace(text, '        VMSTATE_BOOL_V(controller_ack_output, NikonZ72BootConfig, 26),',
        '''        VMSTATE_BOOL_V(controller_ack_output, NikonZ72BootConfig, 26),
        VMSTATE_BOOL(capcom_request, NikonZ72BootConfig),
        VMSTATE_BOOL(capcom_ack, NikonZ72BootConfig),
        VMSTATE_BOOL(capcom_pending, NikonZ72BootConfig),
        VMSTATE_UINT64(capcom_requests, NikonZ72BootConfig),
        VMSTATE_UINT64(capcom_completions, NikonZ72BootConfig),
        VMSTATE_UINT64(capcom_coalesced, NikonZ72BootConfig),
        VMSTATE_TIMER_PTR(capcom_timer, NikonZ72BootConfig),''')
    text = replace(text, '    s->frame_sync_timer = timer_new_ns(QEMU_CLOCK_VIRTUAL, frame_sync_tick, s);',
        '''    s->capcom_timer = timer_new_ns(QEMU_CLOCK_VIRTUAL, capcom_complete, s);
    object_property_add_uint64_ptr(obj, "capcom-requests", &s->capcom_requests, OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(obj, "capcom-completions", &s->capcom_completions, OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(obj, "capcom-coalesced", &s->capcom_coalesced, OBJ_PROP_FLAG_READ);
    s->frame_sync_timer = timer_new_ns(QEMU_CLOCK_VIRTUAL, frame_sync_tick, s);''')
    text = replace(text, '    timer_free(s->frame_sync_timer);',
        '    timer_free(s->capcom_timer);\n    timer_free(s->frame_sync_timer);')
    text = replace(text, '        DEFINE_PROP_BOOL("z62-card-detect", NikonZ72BootConfig,',
        '''        DEFINE_PROP_BOOL("z62-capcom-sync", NikonZ72BootConfig, z62_capcom_sync, false),
        DEFINE_PROP_BOOL("z62-card-detect", NikonZ72BootConfig,''')
    return text


def apply_source(source):
    source = Path(source).resolve()
    if not source.is_relative_to(WORK.resolve()):
        raise ValueError('CAPCOM adapter requires independent r6 workspace')
    path = source / 'hw/arm/nikon-z72.c'
    text = render(path.read_bytes())
    path.write_text(text, encoding='utf-8', newline='\n')
    (path.parent / HEADER.name).write_bytes(HEADER.read_bytes())
    return identity()
