/* SPDX-License-Identifier: GPL-2.0-or-later
 * C1.70 finite channel1 experiment. Actual last RAW -> 30x12 LE-u16 means.
 * 64-byte rows, 61 submitted slots; 0x12000 pitch or explicit zero-pitch bank.
 * Regional box averaging is a functional hypothesis, not Nikon metering math.
 */
#define FINITE_W 30u
#define FINITE_H 12u
#define FINITE_ROW 64u
#define FINITE_BYTES (FINITE_ROW * FINITE_H)
#define FINITE_SLOTS 61u
#define FINITE_START UINT64_C(0x89c48400)
#define FINITE_END UINT64_C(0x8a092400)

static const unsigned finite_offsets[11] = {
    0x2514, 0x2518, 0x2524, 0x253c, 0x2540, 0x2544,
    0x2548, 0x254c, 0x2550, 0x2560, 0x2580
};

static char *finite_reason_get(Object *obj, Error **errp)
{
    Z72InputConfig *s = Z72_INPUT_CONFIG(obj);
    static const char *const names[] = {"reset", "source", "descriptor", "geometry",
        "destination", "memory", "read", "write", "configuration-changed", "success"};
    return g_strdup(s->finite_reason < G_N_ELEMENTS(names) ? names[s->finite_reason] : "invalid");
}

static bool finite_memory(Z72InputConfig *s, hwaddr address, size_t bytes, bool write)
{
    hwaddr translated, available = bytes;
    MemoryRegion *mr = address_space_translate(&s->raw_memory, address,
        &translated, &available, write, MEMTXATTRS_UNSPECIFIED);
    MemoryRegionSection part = memory_region_find(s->raw_root, address, bytes);
    bool good = part.mr && part.mr == mr && memory_region_is_ram(mr) &&
        !memory_region_is_rom(mr) && (!write || !part.readonly) &&
        available >= bytes && int128_ge(part.size, int128_make64(bytes));
    if (part.mr) { memory_region_unref(part.mr); }
    return good;
}

static bool finite_same(Z72InputConfig *s)
{
    for (unsigned i = 0; i < G_N_ELEMENTS(finite_offsets); i++) {
        if (s->finite_config[i] != s->registers[finite_offsets[i] / 4]) { return false; }
    }
    return s->finite_geometry == s->registers[0x22d0 / 4] &&
        s->registers[0x22bc / 4] == 3;
}

static unsigned finite_raw_pixel(const uint8_t *raw, unsigned x, unsigned y)
{
    const uint8_t *p = raw + y * RAW_STRIDE + (x / 2) * 3;
    return (x & 1) ? (p[1] >> 4) | (p[2] << 4) : p[0] | ((p[1] & 15) << 8);
}

static bool finite_prepare(Z72InputConfig *s)
{
    uint32_t *r = s->registers;
    if (!s->raw_accepted || !s->finite_source || !s->raw_root) {
        s->finite_reason = 1; return false;
    }
    if (r[0x2514/4] != 3 || r[0x2518/4] != 1 || r[0x2524/4] ||
        (r[0x253c/4] & ~1u) || r[0x2540/4] != 1 || r[0x2544/4] ||
        r[0x2548/4] != 60 || r[0x254c/4] ||
        (r[0x2580/4] != 0 && r[0x2580/4] != 0x12000)) {
        s->finite_reason = 2; return false;
    }
    if (r[0x22d0/4] != 0x0c1e || r[0x22bc/4] != 3) {
        s->finite_reason = 3; return false;
    }
    uint32_t bank = r[0x253c/4] & 1;
    uint32_t destination = r[(0x2550 + bank*0x10)/4];
    uint32_t pitch = r[0x2580/4];
    /* Preflight the complete declared batch before any destination write. */
    for (unsigned i = 0; i < FINITE_SLOTS; i++) {
        uint64_t address = (uint64_t)destination + (uint64_t)pitch*i;
        if ((address & 3) || address < FINITE_START || address + FINITE_BYTES > FINITE_END) {
            s->finite_reason = 4; return false;
        }
        if (!finite_memory(s, address, FINITE_BYTES, true)) {
            s->finite_reason = 5; return false;
        }
    }
    if (!finite_memory(s, s->finite_source, RAW_BYTES, false)) {
        s->finite_reason = 5; return false;
    }
    g_autofree uint8_t *raw = g_malloc(RAW_BYTES);
    if (address_space_read(&s->raw_memory, s->finite_source, MEMTXATTRS_UNSPECIFIED,
                           raw, RAW_BYTES) != MEMTX_OK) {
        s->finite_reason = 6; return false;
    }
    memset(s->finite_pixels, 0, sizeof(s->finite_pixels));
    for (unsigned y = 0; y < FINITE_H; y++) {
        for (unsigned x = 0; x < FINITE_W; x++) {
            uint64_t sum = 0; unsigned count = 0;
            for (unsigned sy = y*RAW_HEIGHT/FINITE_H; sy < (y+1)*RAW_HEIGHT/FINITE_H; sy++) {
                for (unsigned sx = x*RAW_WIDTH/FINITE_W; sx < (x+1)*RAW_WIDTH/FINITE_W; sx++) {
                    sum += finite_raw_pixel(raw, sx, sy); count++;
                }
            }
            stw_le_p(s->finite_pixels + y*FINITE_ROW + x*2, (sum + count/2)/count);
        }
    }
    for (unsigned i = 0; i < G_N_ELEMENTS(finite_offsets); i++) {
        s->finite_config[i] = r[finite_offsets[i]/4];
    }
    s->finite_geometry = r[0x22d0/4];
    s->finite_destination = destination;
    s->finite_pitch = pitch;
    s->finite_index = 0;
    s->finite_active = true;
    s->finite_done = false;
    return true;
}

static void finite_enable(void *opaque, int line, int level)
{
    Z72InputConfig *s = opaque;
    if (!s->z62_layout || !s->functional_finite_stats) { return; }
    bool changed = s->finite_enabled != !!level;
    s->finite_enabled = !!level;
    if (!level) {
        s->finite_active = s->finite_done = s->finite_rearm = false;
        s->finite_index = 0;
    } else if (changed) {
        s->finite_rearm = true;
    }
}

static void finite_commit(void *opaque, int line, int level)
{
    Z72InputConfig *s = opaque;
    if (level && s->finite_enabled) { s->finite_rearm = true; }
}

static void finite_frame(void *opaque, int line, int level)
{
    Z72InputConfig *s = opaque;
    bool rising = level && !s->finite_clock_level;
    s->finite_clock_level = !!level;
    if (!rising || !s->z62_layout || !s->functional_finite_stats || !s->finite_enabled) { return; }
    /* Other modes are intentionally outside this first finite-capture contract. */
    if (s->registers[0x2548/4] != 60) { return; }
    bool same = finite_same(s);
    if (s->finite_rearm) {
        s->finite_rearm = false;
        if ((!s->finite_active && !s->finite_done) || !same) {
            s->finite_active = false;
            s->finite_attempts++;
            if (!finite_prepare(s)) { s->finite_rejected++; return; }
        }
    }
    if (!s->finite_active) { return; }
    if (s->finite_index >= FINITE_SLOTS) {
        s->finite_active = false;
        s->finite_reason = 2;
        s->finite_rejected++;
        return;
    }
    if (!finite_same(s)) {
        s->finite_active = false;
        s->finite_reason = 8;
        s->finite_rejected++;
        return;
    }
    uint64_t address = (uint64_t)s->finite_destination + (uint64_t)s->finite_pitch*s->finite_index;
    if (!finite_memory(s, address, FINITE_BYTES, true) ||
        address_space_write(&s->raw_memory, address, MEMTXATTRS_UNSPECIFIED,
                            s->finite_pixels, FINITE_BYTES) != MEMTX_OK) {
        s->finite_active = false;
        s->finite_reason = 7;
        s->finite_rejected++;
        return;
    }
    s->finite_frames++;
    s->finite_bytes += FINITE_BYTES;
    s->finite_index++;
    s->finite_reason = 9;
    qemu_set_irq(s->finite_ready_irq, 1);
    qemu_set_irq(s->finite_ready_irq, 0);
    if (s->finite_index == FINITE_SLOTS) {
        s->finite_active = false;
        s->finite_done = true;
        s->finite_batches++;
        qemu_set_irq(s->finite_complete_irq, 1);
        qemu_set_irq(s->finite_complete_irq, 0);
    }
}

static void finite_reset(Z72InputConfig *s)
{
    s->finite_enabled = s->finite_active = s->finite_done = false;
    s->finite_clock_level = s->finite_rearm = false;
    s->finite_source = s->finite_destination = s->finite_pitch = s->finite_index = 0;
    s->finite_geometry = s->finite_reason = 0;
    memset(s->finite_config, 0, sizeof(s->finite_config));
    memset(s->finite_pixels, 0, sizeof(s->finite_pixels));
    s->finite_attempts = s->finite_frames = s->finite_batches = s->finite_rejected = s->finite_bytes = 0;
    qemu_set_irq(s->finite_ready_irq, 0);
    qemu_set_irq(s->finite_complete_irq, 0);
}

static bool finite_vmstate_needed(void *opaque)
{
    Z72InputConfig *s = opaque;
    return s->z62_layout && s->functional_finite_stats;
}

static const VMStateDescription finite_vmstate = {
    .name = TYPE_Z72_INPUT_CONFIG "/finite-stats", .version_id = 1, .minimum_version_id = 1,
    .needed = finite_vmstate_needed,
    .fields = (const VMStateField[]) {
        VMSTATE_BOOL(finite_enabled, Z72InputConfig), VMSTATE_BOOL(finite_active, Z72InputConfig),
        VMSTATE_BOOL(finite_done, Z72InputConfig), VMSTATE_BOOL(finite_clock_level, Z72InputConfig),
        VMSTATE_BOOL(finite_rearm, Z72InputConfig), VMSTATE_UINT32(finite_source, Z72InputConfig),
        VMSTATE_UINT32(finite_destination, Z72InputConfig), VMSTATE_UINT32(finite_pitch, Z72InputConfig),
        VMSTATE_UINT32(finite_index, Z72InputConfig), VMSTATE_UINT32(finite_geometry, Z72InputConfig),
        VMSTATE_UINT32(finite_reason, Z72InputConfig), VMSTATE_UINT32_ARRAY(finite_config, Z72InputConfig, 11),
        VMSTATE_UINT8_ARRAY(finite_pixels, Z72InputConfig, 768),
        VMSTATE_UINT64(finite_attempts, Z72InputConfig), VMSTATE_UINT64(finite_frames, Z72InputConfig),
        VMSTATE_UINT64(finite_batches, Z72InputConfig), VMSTATE_UINT64(finite_rejected, Z72InputConfig),
        VMSTATE_UINT64(finite_bytes, Z72InputConfig), VMSTATE_END_OF_LIST()
    }
};
