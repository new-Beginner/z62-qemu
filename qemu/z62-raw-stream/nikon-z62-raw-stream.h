/* SPDX-License-Identifier: GPL-2.0-or-later
 * Functional channel2 RAW source for the original Z62 C1.70 consumer.
 * Actual four-slot DMA -> bank4 bit8 -> IRQ96 -> task4000 -> C26A0AC4.
 * Clock cadence and packed12 remain hypotheses. No ISP/metadata is claimed.
 */
static bool raw_stream_supported(NikonZ72BootConfig *s)
{
    return s->z62_raw_stream && s->z62_card_detect && s->master_role;
}

static bool raw_stream_running(NikonZ72BootConfig *s)
{
    return raw_stream_supported(s) && s->raw_stream_started &&
           (*boot_config_value(s, 0x20068010) & 0x200) &&
           !(*boot_config_value(s, 0x20068018) & 0x200);
}

static bool raw_stream_active_get(Object *obj, Error **errp)
{
    return raw_stream_running(NIKON_Z72_BOOT_CONFIG(obj));
}

static void raw_stream_control(NikonZ72BootConfig *s, hwaddr address, uint32_t value)
{
    if (!raw_stream_supported(s)) {
        return;
    }
    if (address == 0x20068008 && (value & 0x200)) {
        s->raw_stream_started = true;
    } else if ((address == 0x20068014 || address == 0x20068018) && (value & 0x200)) {
        s->raw_stream_started = false;
    }
}

static void raw_stream_dma_done(void *opaque, int line, int level)
{
    NikonZ72BootConfig *s = opaque;
    bool rising = level && !s->raw_stream_dma_level;
    qemu_set_irq(s->raw_stream_sensor_irq, level);
    s->raw_stream_dma_level = level != 0;
    if (!rising || !raw_stream_supported(s)) {
        return;
    }
    /* Legacy explicit submissions still reach the existing sensor bridge.
     * Only the frame transaction owned by this source can signal channel2. */
    if (!s->raw_stream_waiting || !raw_stream_running(s)) {
        s->raw_stream_unrelated++;
        return;
    }
    s->raw_stream_completed = true;
    s->raw_stream_frames++;
    *boot_config_value(s, 0x20068290) |= 0x100;
    input_update_irqs(s);
}

static void raw_stream_frame(void *opaque, int line, int level)
{
    NikonZ72BootConfig *s = opaque;
    bool rising = level && !s->raw_stream_frame_level;
    s->raw_stream_frame_level = level != 0;
    if (!rising || !raw_stream_running(s)) {
        return;
    }
    /* Do not overwrite a batch whose completion is still unconsumed. This
     * bounded backpressure model does not pretend to reproduce overrun silicon. */
    if (*boot_config_value(s, 0x20068290) & 0x100) {
        s->raw_stream_blocked++;
        return;
    }
    s->raw_stream_attempts++;
    s->raw_stream_completed = false;
    s->raw_stream_waiting = true;
    qemu_set_irq(s->raw_submit_irq, 0);
    qemu_set_irq(s->raw_submit_irq, 1);
    qemu_set_irq(s->raw_submit_irq, 0);
    s->raw_stream_waiting = false;
    if (!s->raw_stream_completed) {
        s->raw_stream_failed++;
    }
}

static void raw_stream_reset(NikonZ72BootConfig *s)
{
    s->raw_stream_started = s->raw_stream_waiting = s->raw_stream_completed = false;
    s->raw_stream_frame_level = s->raw_stream_dma_level = false;
    s->raw_stream_attempts = s->raw_stream_frames = s->raw_stream_failed = 0;
    s->raw_stream_blocked = s->raw_stream_unrelated = 0;
    qemu_set_irq(s->raw_stream_sensor_irq, 0);
}
