"""Independent capture-contact GPIO extension over frozen r9."""
from pathlib import Path
import reference_updates as reference

ROOT = Path(__file__).resolve().parents[1]
VERSION = '2026.10.29-r13'
WORK = ROOT / '.build' / ('z62-capture-contacts-' + VERSION)
HEADER = ROOT / 'qemu/z62-capture-contacts/nikon-z62-capture-contacts.h'
INPUT_SHA = 'c543a72929474488896000fc43add9e982403b5b504368e9bdb76eb53ab4589a'


def identity():
    return {'schema': 1, 'version': VERSION, 'input_sha256': INPUT_SHA,
            'adapter_sha256': reference.sha(Path(__file__).read_bytes()),
            'header_sha256': reference.sha(HEADER.read_bytes()),
            'default_enabled': False, 'input_register': '0x04282014',
            'input_bits': [11, 12], 'ext_indices': [4, 5], 'irqs': [69, 70],
            'native_binding_evidence': 'analysis/z62-capture-r13/gpio-bindings/trace.json',
            'guest_software_patched': False, 'photo_capture_verified': False}


def render(data):
    if reference.sha(data) != INPUT_SHA:
        raise ValueError('Capture contacts require exact frozen r9 board source')
    text = data.decode('utf-8')
    replace = reference.replace_once
    text = replace(text, '    bool z62_capcom_sync, capcom_request, capcom_ack, capcom_pending;',
        '''    bool z62_capcom_sync, capcom_request, capcom_ack, capcom_pending;
    bool z62_capture_contacts;
    uint32_t capture_contact_levels;
    uint64_t capture_contact_edges, capture_contact_irq_events;''')
    text = replace(text, '#include "nikon-z62-capcom.h"',
        '#include "nikon-z62-capture-contacts.h"\n#include "nikon-z62-capcom.h"')
    text = replace(text, '    capcom_update_irq(s);',
        '    capcom_update_irq(s);\n    capture_contacts_update_irq(s);')
    text = replace(text, '    if (capcom_active(s)) {\n        hwaddr address = boot_config_addresses[word->index];',
        '''    if (capture_contacts_active(s) && boot_config_addresses[word->index] == 0x04282014) {
        value = (value & ~0x1800u) | ((s->capture_contact_levels & 3) << 11);
    }
    if (capcom_active(s)) {
        hwaddr address = boot_config_addresses[word->index];''')
    text = replace(text, '    capcom_write(s, address, value);',
        '''    if (capture_contacts_write(s, address, value)) {
        return;
    }
    capcom_write(s, address, value);''')
    text = replace(text, '    capcom_reset(s);',
        '    capcom_reset(s);\n    capture_contacts_reset(s);')
    text = replace(text, '    .version_id = 42,\n    .minimum_version_id = 42,',
        '    .version_id = 43,\n    .minimum_version_id = 43,')
    text = replace(text, '        VMSTATE_BOOL(capcom_request, NikonZ72BootConfig),',
        '''        VMSTATE_UINT32(capture_contact_levels, NikonZ72BootConfig),
        VMSTATE_UINT64(capture_contact_edges, NikonZ72BootConfig),
        VMSTATE_UINT64(capture_contact_irq_events, NikonZ72BootConfig),
        VMSTATE_BOOL(capcom_request, NikonZ72BootConfig),''')
    text = replace(text, '    s->capcom_timer = timer_new_ns(QEMU_CLOCK_VIRTUAL, capcom_complete, s);',
        '''    qdev_init_gpio_in_named(DEVICE(obj), capture_contact_input, "capture-contact", 2);
    object_property_add_uint32_ptr(obj, "capture-contact-levels", &s->capture_contact_levels, OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(obj, "capture-contact-edges", &s->capture_contact_edges, OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(obj, "capture-contact-irq-events", &s->capture_contact_irq_events, OBJ_PROP_FLAG_READ);
    s->capcom_timer = timer_new_ns(QEMU_CLOCK_VIRTUAL, capcom_complete, s);''')
    text = replace(text, '        DEFINE_PROP_BOOL("z62-capcom-sync",',
        '''        DEFINE_PROP_BOOL("z62-capture-contacts", NikonZ72BootConfig, z62_capture_contacts, false),
        DEFINE_PROP_BOOL("z62-capcom-sync",''')
    return text


def apply_source(source):
    source = Path(source).resolve()
    if not source.is_relative_to(WORK.resolve()):
        raise ValueError('Capture contacts require independent r13 workspace')
    board = source / 'hw/arm/nikon-z72.c'
    board.write_text(render(board.read_bytes()), encoding='utf-8', newline='\n')
    (board.parent / HEADER.name).write_bytes(HEADER.read_bytes())
    return identity()
