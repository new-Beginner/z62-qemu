/* SPDX-License-Identifier: GPL-2.0-or-later
 * Observed C1.70 six-slot statistics profile: sum/count, scalar, three planes.
 * Every completion follows real bounded DMA. Other input engines are separate.
 */
#define CONTINUOUS_CONFIG_WORDS 73u
#define CONTINUOUS_SLOTS 6u
static const unsigned continuous_dma_offsets[] = {
    0x14, 0x18, 0x24, 0x3c, 0x40, 0x44, 0x48, 0x4c, 0x50, 0x60, 0x80
};
static const unsigned continuous_extra_offsets[] = {0x54, 0x58, 0x5c, 0x64, 0x68, 0x6c};
static const uint32_t continuous_base[5] = {0x88e37000, 0x88e73000, 0x88edf000, 0x88ef1000, 0x88f03000};
static const uint32_t continuous_pitch[5] = {0xa000, 0x12000, 0x36000, 0x36000, 0x36000};
static const uint32_t continuous_bytes[5] = {480*20, 64*20, 128*40, 128*40, 128*40};

static char *continuous_reason_get(Object *obj, Error **errp)
{
    Z72InputConfig *s = Z72_INPUT_CONFIG(obj);
    static const char *const names[] = {"reset", "source", "descriptor", "geometry",
        "destination", "memory", "overlap", "io", "configuration-changed", "success", "status"};
    return g_strdup(s->continuous_reason < G_N_ELEMENTS(names) ? names[s->continuous_reason] : "invalid");
}

static void continuous_snapshot(Z72InputConfig *s, uint32_t values[CONTINUOUS_CONFIG_WORDS])
{
    unsigned n = 0;
    for (unsigned ch = 0; ch < 5; ch++) {
        unsigned base = 0x2400 + ch*0x100;
        for (unsigned i = 0; i < G_N_ELEMENTS(continuous_dma_offsets); i++) {
            values[n++] = s->registers[(base+continuous_dma_offsets[i])/4];
        }
        if (ch >= 2) {
            for (unsigned i = 0; i < G_N_ELEMENTS(continuous_extra_offsets); i++) {
                values[n++] = s->registers[(base+continuous_extra_offsets[i])/4];
            }
        }
    }
    g_assert(n == CONTINUOUS_CONFIG_WORDS);
}

static bool continuous_geometry(Z72InputConfig *s)
{
    static const uint32_t geometry[][2] = {
        {0x2204,1}, {0x2268,0x14}, {0x226c,0xa}, {0x2270,0x42042},
        {0x2274,0x42042}, {0x2278,0x141e},
        {0x22bc,3}, {0x22c0,0x10d1b}, {0x22c4,6}, {0x22c8,2}, {0x22cc,0xc832}, {0x22d0,0x141e}
    };
    for (unsigned i = 0; i < G_N_ELEMENTS(geometry); i++) {
        if (s->registers[geometry[i][0]/4] != geometry[i][1]) { return false; }
    }
    for (unsigned ch = 0; ch < 3; ch++) {
        unsigned base = 0x22d4 + ch*0x18;
        if (s->registers[base/4] != ((ch+1)*0x100+3) || s->registers[(base+4)/4] != 0x10e39 ||
            s->registers[(base+8)/4] != 0x26 || s->registers[(base+12)/4] != 0x18 ||
            s->registers[(base+16)/4] != 0x6018 || s->registers[(base+20)/4] != 0x283c) { return false; }
    }
    return true;
}

static bool continuous_profile(Z72InputConfig *s)
{
    if (!s->raw_root) { s->continuous_reason=1; return false; }
    for (unsigned ch = 0; ch < 5; ch++) {
        uint32_t *r = &s->registers[(0x2400+ch*0x100)/4];
        if (r[0x14/4] != 3 || r[0x18/4] != 1 || r[0x24/4] || (r[0x3c/4] & ~1u) ||
            r[0x40/4] != 1 || r[0x44/4] || r[0x48/4] != 5 || r[0x4c/4] ||
            r[0x80/4] != continuous_pitch[ch]) { s->continuous_reason=2; return false; }
        if (r[0x50/4] != continuous_base[ch] || r[0x60/4] != continuous_base[ch]) {
            s->continuous_reason=4; return false;
        }
        if (ch >= 2) {
            for (unsigned i = 0; i < G_N_ELEMENTS(continuous_extra_offsets); i++) {
                if (r[continuous_extra_offsets[i]/4] != continuous_base[ch]) {
                    s->continuous_reason=4; return false;
                }
            }
        }
    }
    if (!continuous_geometry(s)) { s->continuous_reason=3; return false; }
    for (unsigned ch = 0; ch < 5; ch++) {
        for (unsigned slot = 0; slot < CONTINUOUS_SLOTS; slot++) {
            uint64_t address = (uint64_t)continuous_base[ch] + (uint64_t)continuous_pitch[ch]*slot;
            if (!finite_memory(s, address, continuous_bytes[ch], true)) {
                s->continuous_reason=5; return false;
            }
        }
    }
    return true;
}

static void continuous_enable(void *opaque, int line, int level)
{
    Z72InputConfig *s = opaque;
    finite_enable(opaque, line, level);
    if (!s->z62_layout || !s->functional_continuous_stats) { return; }
    if (s->continuous_enabled != !!level) {
        s->continuous_active=false;
        s->continuous_index=0;
        s->continuous_seen_raw=s->raw_accepted;
        s->continuous_rearm=!!level;
    }
    s->continuous_enabled=!!level;
}

static void continuous_commit(void *opaque, int line, int level)
{
    Z72InputConfig *s = opaque;
    finite_commit(opaque, line, level);
    if (level && s->functional_continuous_stats && s->continuous_enabled) { s->continuous_rearm=true; }
}

static void continuous_frame(void *opaque, int line, int level)
{
    Z72InputConfig *s = opaque;
    g_autofree uint8_t *raw=NULL;
    bool edge = level && !s->continuous_clock_level;
    s->continuous_clock_level=!!level;
    finite_frame(opaque, line, level);
    if (!edge || !s->z62_layout || !s->functional_continuous_stats || !s->continuous_enabled) { return; }
    /* The established finite 61-slot mode retains its own implementation. */
    if (s->registers[0x2548/4] == 60) { s->continuous_active=false; return; }
    uint32_t config[CONTINUOUS_CONFIG_WORDS];
    continuous_snapshot(s, config);
    bool same = memcmp(config,s->continuous_config,sizeof(config)) == 0;
    if (s->continuous_rearm) {
        s->continuous_rearm=false;
        if (!s->continuous_active || !same) {
            s->continuous_active=false;
            if (!continuous_profile(s)) { s->continuous_rejected++; return; }
            memcpy(s->continuous_config,config,sizeof(config));
            s->continuous_index=0;
            s->continuous_active=true;
        }
    } else if (s->continuous_active && (!same || !continuous_geometry(s))) {
        s->continuous_active=false;
        s->continuous_reason=8;
        s->continuous_rejected++;
        return;
    }
    if (!s->continuous_active) { return; }
    if (!s->raw_accepted || !s->continuous_source) { s->continuous_reason=1; return; }
    if (s->raw_accepted == s->continuous_seen_raw) { return; }
    uint8_t status[4];
    if (address_space_read(&s->raw_memory,0x20068270,MEMTXATTRS_UNSPECIFIED,status,4) != MEMTX_OK) {
        s->continuous_reason=10; s->continuous_rejected++; return;
    }
    /* Preserve any unacknowledged sample or six-slot batch, even if masked. */
    if (ldl_le_p(status) & 0xa0) { s->continuous_blocked++; return; }
    s->continuous_attempts++;
    s->continuous_seen_raw=s->raw_accepted;
    uint64_t source=s->continuous_source;
    if (!s->raw_accepted || !source || !s->raw_root) { s->continuous_reason=1; goto rejected; }
    if (!continuous_profile(s)) { goto rejected; }
    if (s->continuous_index >= CONTINUOUS_SLOTS || !finite_memory(s,source,Z62_STATS_RAW_BYTES,false)) {
        s->continuous_reason=5; goto rejected;
    }
    for (unsigned ch=0;ch<5;ch++) {
        for (unsigned slot=0;slot<CONTINUOUS_SLOTS;slot++) {
            uint64_t dst=(uint64_t)continuous_base[ch]+(uint64_t)continuous_pitch[ch]*slot;
            if (source < dst+continuous_bytes[ch] && dst < source+Z62_STATS_RAW_BYTES) {
                s->continuous_reason=6; goto rejected;
            }
        }
    }
    raw=g_malloc(Z62_STATS_RAW_BYTES);
    if (address_space_read(&s->raw_memory,source,MEMTXATTRS_UNSPECIFIED,raw,Z62_STATS_RAW_BYTES) != MEMTX_OK ||
        !z62_statistics_calculate(raw,Z62_STATS_RAW_BYTES,&s->continuous_pixels)) {
        s->continuous_reason=7; goto rejected;
    }
    const uint8_t *planes[5] = {s->continuous_pixels.sums,s->continuous_pixels.scalar,
        s->continuous_pixels.rgb[0],s->continuous_pixels.rgb[1],s->continuous_pixels.rgb[2]};
    for (unsigned ch=0;ch<5;ch++) {
        uint64_t dst=(uint64_t)continuous_base[ch]+(uint64_t)continuous_pitch[ch]*s->continuous_index;
        if (address_space_write(&s->raw_memory,dst,MEMTXATTRS_UNSPECIFIED,planes[ch],continuous_bytes[ch]) != MEMTX_OK) {
            s->continuous_reason=7; goto rejected;
        }
    }
    s->continuous_frames++;
    s->continuous_bytes+=sizeof(s->continuous_pixels);
    s->continuous_index++;
    s->continuous_reason=9;
    qemu_set_irq(s->finite_ready_irq,1); qemu_set_irq(s->finite_ready_irq,0);
    if (s->continuous_index == CONTINUOUS_SLOTS) {
        s->continuous_index=0;
        s->continuous_batches++;
        qemu_set_irq(s->finite_complete_irq,1); qemu_set_irq(s->finite_complete_irq,0);
    }
    return;
rejected:
    s->continuous_rejected++;
}

static void continuous_reset(Z72InputConfig *s)
{
    s->continuous_enabled=s->continuous_active=s->continuous_clock_level=s->continuous_rearm=false;
    s->continuous_index=s->continuous_reason=s->continuous_source=0;
    s->continuous_seen_raw=s->continuous_attempts=s->continuous_frames=s->continuous_batches=0;
    s->continuous_rejected=s->continuous_bytes=s->continuous_blocked=0;
    memset(s->continuous_config,0,sizeof(s->continuous_config));
    memset(&s->continuous_pixels,0,sizeof(s->continuous_pixels));
}

static bool continuous_vmstate_needed(void *opaque)
{
    Z72InputConfig *s = opaque;
    return s->z62_layout && s->functional_continuous_stats;
}

static int continuous_post_load(void *opaque, int version_id)
{
    Z72InputConfig *s = opaque;
    return s->continuous_index < CONTINUOUS_SLOTS && s->continuous_reason <= 10 ? 0 : -EINVAL;
}

static const VMStateDescription continuous_vmstate = {
    .name=TYPE_Z72_INPUT_CONFIG "/continuous-stats", .version_id=1, .minimum_version_id=1,
    .needed=continuous_vmstate_needed, .post_load=continuous_post_load,
    .fields=(const VMStateField[]) {
        VMSTATE_BOOL(continuous_enabled,Z72InputConfig), VMSTATE_BOOL(continuous_active,Z72InputConfig),
        VMSTATE_BOOL(continuous_clock_level,Z72InputConfig), VMSTATE_BOOL(continuous_rearm,Z72InputConfig),
        VMSTATE_UINT32(continuous_index,Z72InputConfig), VMSTATE_UINT32(continuous_reason,Z72InputConfig),
        VMSTATE_UINT32(continuous_source,Z72InputConfig),
        VMSTATE_UINT32_ARRAY(continuous_config,Z72InputConfig,CONTINUOUS_CONFIG_WORDS),
        VMSTATE_UINT64(continuous_seen_raw,Z72InputConfig), VMSTATE_UINT64(continuous_attempts,Z72InputConfig),
        VMSTATE_UINT64(continuous_frames,Z72InputConfig), VMSTATE_UINT64(continuous_batches,Z72InputConfig),
        VMSTATE_UINT64(continuous_rejected,Z72InputConfig), VMSTATE_UINT64(continuous_bytes,Z72InputConfig),
        VMSTATE_UINT64(continuous_blocked,Z72InputConfig), VMSTATE_END_OF_LIST()
    }
};
