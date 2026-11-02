/* SPDX-License-Identifier: GPL-2.0-or-later
 * C1.70 native capture contacts, separate from the controller key-message path.
 * GPIO resources 0x58/0x59: 04282014 bits11/12, EXT4/5, IRQ69/70.
 * The original ISR reads the level and rearms the opposite edge (mode2).
 * A logical asserted contact is high here; MCU PG1/PG13 are active low.
 * No capture completion, software event, sensor data or file is manufactured.
 */
static bool capture_contacts_active(NikonZ72BootConfig *s)
{
    return s->z62_capture_contacts && s->z62_card_detect && s->master_role;
}

static void capture_contacts_update_irq(NikonZ72BootConfig *s)
{
    if (capture_contacts_active(s) && s->intc) {
        uint32_t pending = *boot_config_value(s, 0x0426f008);
        uint32_t mask = *boot_config_value(s, 0x0426f000);
        for (unsigned i = 0; i < 2; i++) {
            qemu_set_irq(qdev_get_gpio_in(s->intc, 69 + i - 32),
                         !!(pending & ~mask & (1u << (4 + i))));
        }
    }
}

static void capture_contact_input(void *opaque, int line, int level)
{
    NikonZ72BootConfig *s = opaque;
    if (!capture_contacts_active(s) || line < 0 || line >= 2 ||
        resettable_is_in_reset(OBJECT(s))) {
        return;
    }
    uint32_t contact = 1u << line;
    uint32_t ext = 1u << (line + 4);
    bool asserted = level != 0;
    if (!!(s->capture_contact_levels & contact) == asserted) {
        return;
    }
    s->capture_contact_levels = (s->capture_contact_levels & ~contact) |
                               (asserted ? contact : 0);
    s->capture_contact_edges++;
    if (!!(*boot_config_value(s, 0x0426f014) & ext) == asserted) {
        *boot_config_value(s, 0x0426f008) |= ext;
        s->capture_contact_irq_events++;
    }
    capture_contacts_update_irq(s);
}

static bool capture_contacts_write(NikonZ72BootConfig *s, hwaddr address,
                                   uint32_t value)
{
    if (!capture_contacts_active(s)) {
        return false;
    }
    uint32_t *pending = boot_config_value(s, 0x0426f008);
    if (address == 0x0426f008) {
        uint32_t preserved = 0x30u | (s->controller_connected ? 0xcu : 0) |
                             (s->z62_capcom_sync ? 1u : 0);
        *pending = (value & ~preserved) | (*pending & preserved);
        return true;
    }
    if (address == 0x0426f010) {
        *pending &= ~(value & 0x30u);
        capture_contacts_update_irq(s);
    }
    return false;
}

static void capture_contacts_reset(NikonZ72BootConfig *s)
{
    s->capture_contact_levels = 0;
    s->capture_contact_edges = s->capture_contact_irq_events = 0;
    capture_contacts_update_irq(s);
}
