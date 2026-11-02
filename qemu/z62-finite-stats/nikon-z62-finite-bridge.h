/* SPDX-License-Identifier: GPL-2.0-or-later */
static void finite_bridge_control(NikonZ72BootConfig *s, hwaddr address, uint32_t value)
{
    if (!s->z62_finite_stats || !s->z62_card_detect || !s->master_role) { return; }
    if (address == 0x20068008 && (value & 0x10)) {
        s->finite_started = true;
    } else if ((address == 0x2006800c || address == 0x20068014) && (value & 0x10)) {
        s->finite_started = false;
    }
    /* +18 is a separately armed command-notification word (1020A524),
     * and remains 0x1c during the observed native finite capture. */
    qemu_set_irq(s->finite_enable_irq, s->finite_started &&
        (*boot_config_value(s, 0x20068010) & 0x10));
    if (address == 0x20068100 && (value & 8)) {
        qemu_set_irq(s->finite_commit_irq, 1);
        qemu_set_irq(s->finite_commit_irq, 0);
    }
}

static void finite_bridge_frame(NikonZ72BootConfig *s)
{
    if (s->z62_finite_stats && s->master_role && s->z62_card_detect) {
        qemu_set_irq(s->finite_frame_irq, 1);
        qemu_set_irq(s->finite_frame_irq, 0);
    }
}
