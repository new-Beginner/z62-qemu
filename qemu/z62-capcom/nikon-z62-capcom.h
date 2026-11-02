/* SPDX-License-Identifier: GPL-2.0-or-later
 * Z62 CAPCOM functional request/ack peer. Derived from the Z7 project's
 * documented GPIO contract; independently anchored to C1.70 live handles.
 * Request: 04282018 bit8; acknowledge: 04282014 bit7, EXT0 / IRQ65.
 * The 100us latency is an explicit hypothesis, not mechanical emulation.
 */
static bool capcom_active(NikonZ72BootConfig *s)
{
    return s->z62_capcom_sync && s->z62_card_detect && s->master_role;
}

static void capcom_update_irq(NikonZ72BootConfig *s)
{
    if (capcom_active(s) && s->intc) {
        qemu_set_irq(qdev_get_gpio_in(s->intc, 65 - 32),
                    (*boot_config_value(s, 0x0426f008) &
                     ~*boot_config_value(s, 0x0426f000) & 1) != 0);
    }
}

static void capcom_level(NikonZ72BootConfig *s, bool level)
{
    bool changed = level != s->capcom_ack;
    s->capcom_ack = level;
    if (changed && (!!(*boot_config_value(s, 0x0426f014) & 1) == level)) {
        *boot_config_value(s, 0x0426f008) |= 1;
    }
    capcom_update_irq(s);
}

static void capcom_complete(void *opaque)
{
    NikonZ72BootConfig *s = opaque;
    if (!capcom_active(s) || !s->capcom_pending) {
        return;
    }
    s->capcom_pending = false;
    s->capcom_completions++;
    capcom_level(s, true);
}

static void capcom_write(NikonZ72BootConfig *s, hwaddr address, uint32_t value)
{
    if (!capcom_active(s)) {
        return;
    }
    if (address == 0x0426f010) {
        *boot_config_value(s, 0x0426f008) &= ~(value & 1);
        capcom_update_irq(s);
    }
    if (address == 0x04282018 && (value & (1u << 24))) {
        bool level = !!(value & 0x100);
        bool edge = level && !s->capcom_request;
        s->capcom_request = level;
        if (edge) {
            s->capcom_requests++;
            if (s->capcom_pending || (*boot_config_value(s, 0x0426f008) & 1)) {
                s->capcom_coalesced++;
                return;
            }
            capcom_level(s, false);
            s->capcom_pending = true;
            timer_mod(s->capcom_timer,
                      qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) + 100000);
        }
    }
}

static void capcom_reset(NikonZ72BootConfig *s)
{
    timer_del(s->capcom_timer);
    s->capcom_request = s->capcom_ack = s->capcom_pending = false;
    s->capcom_requests = s->capcom_completions = s->capcom_coalesced = 0;
    capcom_update_irq(s);
}
