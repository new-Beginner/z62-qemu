/* SPDX-License-Identifier: GPL-2.0-or-later
 * Functional input boundary tied to an actual native RAW transaction.
 * Original route: bank0 bit0 -> IRQ94 -> 10238FF2 -> task1 -> 041A000F.
 * This is an ingress boundary, not a statistics/ISP/photo completion.
 * Its alignment with successful DMA is a functional timing hypothesis.
 */
static void raw_boundary_frame(void *opaque, int line, int level)
{
    NikonZ72BootConfig *s = opaque;
    uint64_t before = s->raw_stream_frames;

    raw_stream_frame(opaque, line, level);
    if (!s->z62_raw_boundary || s->raw_stream_frames == before) {
        return;
    }
    /* raw_stream_frames changes only for a successful, owned master RAW DMA.
     * Preserve the existing status latch, mask and W1C semantics. */
    if (*boot_config_value(s, 0x20068210) & 1) {
        s->raw_boundary_coalesced++;
    }
    s->raw_boundary_events++;
    *boot_config_value(s, 0x20068210) |= 1;
    input_update_irqs(s);
}

static void raw_boundary_reset(NikonZ72BootConfig *s)
{
    s->raw_boundary_events = 0;
    s->raw_boundary_coalesced = 0;
}
