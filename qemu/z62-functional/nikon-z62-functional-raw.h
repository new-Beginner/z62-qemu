/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Explicit experimental packed12 static input, NOT established silicon packing.
 * Included after Z72InputConfig. No timer, guest state fixup or sensor IRQ. */
#define RAW_WIDTH 1514u
#define RAW_HEIGHT 1006u
#define RAW_STRIDE 2272u
#define RAW_BYTES (RAW_HEIGHT * RAW_STRIDE)
#define RAW_POOL_START UINT64_C(0x82c00000)
#define RAW_POOL_END (RAW_POOL_START + UINT64_C(0x082bc400))

enum { RAW_RESET, RAW_DISABLED, RAW_LAYOUT, RAW_CONFIG, RAW_GEOMETRY,
       RAW_STRIDE_BAD, RAW_ADDRESS, RAW_OVERLAP, RAW_NOT_RAM, RAW_IO,
       RAW_SUCCESS };

static char *raw_reason_get(Object *obj, Error **errp)
{
    static const char *const names[] = {
        "reset", "disabled", "not-z62", "config", "geometry", "stride",
        "address", "overlap", "not-writable-ram", "dma-error", "success"
    };
    Z72InputConfig *s = Z72_INPUT_CONFIG(obj);
    return g_strdup(s->raw_reason < G_N_ELEMENTS(names) ?
                    names[s->raw_reason] : "invalid-migrated-reason");
}

static void raw_reject(Z72InputConfig *s, uint32_t reason)
{
    s->raw_rejected++;
    s->raw_reason = reason;
}

static bool raw_writable(Z72InputConfig *s, hwaddr addr)
{
    hwaddr translated, available = RAW_BYTES;
    MemoryRegion *mr = address_space_translate(&s->raw_memory, addr,
        &translated, &available, true, MEMTXATTRS_UNSPECIFIED);
    /* Check flattened readonly attribute as well as backing RAM type; never
     * let an address-space write dispatch into an MMIO device or ROM alias. */
    MemoryRegionSection section = memory_region_find(s->raw_root, addr, RAW_BYTES);
    bool valid = section.mr && section.mr == mr && !section.readonly &&
        memory_region_is_ram(mr) && !memory_region_is_rom(mr) &&
        available >= RAW_BYTES &&
        int128_ge(section.size, int128_make64(RAW_BYTES));
    if (section.mr) {
        memory_region_unref(section.mr);
    }
    return valid;
}

static void raw_submit(void *opaque, int line, int level)
{
    Z72InputConfig *s = opaque;
    uint32_t dst[4];
    bool edge = level && !s->raw_submit_level;
    s->raw_submit_level = level != 0;
    if (!edge) {
        return;
    }
    if (!s->functional_raw) {
        raw_reject(s, RAW_DISABLED);
        return;
    }
    if (!s->z62_layout || !s->raw_root) {
        raw_reject(s, RAW_LAYOUT);
        return;
    }
    /* Submit is the ONLY trigger/gate. The existing Z62 input control
     * 20069514 must equal the observed 6. This is not autonomous streaming
     * and does not infer the unproven hardware meaning of individual bits. */
    if (s->registers[0x1514 / 4] != 6) {
        raw_reject(s, RAW_CONFIG);
        return;
    }
    if (s->registers[0x1518 / 4] != 0x05ea0000 ||
        s->registers[0x151c / 4] != 0x03ee0000) {
        raw_reject(s, RAW_GEOMETRY);
        return;
    }
    if (s->registers[0x1a08 / 4] != RAW_STRIDE) {
        raw_reject(s, RAW_STRIDE_BAD);
        return;
    }
    unsigned bank = s->registers[0x1a3c / 4] & 1;
    for (unsigned i = 0; i < 4; i++) {
        dst[i] = s->registers[(0x1a50 + bank * 16 + i * 4) / 4];
        if (!dst[i] || (dst[i] & 3) || dst[i] < RAW_POOL_START ||
            (uint64_t)dst[i] + RAW_BYTES > RAW_POOL_END) {
            raw_reject(s, RAW_ADDRESS);
            return;
        }
        for (unsigned j = 0; j < i; j++) {
            if ((uint64_t)dst[i] < (uint64_t)dst[j] + RAW_BYTES &&
                (uint64_t)dst[j] < (uint64_t)dst[i] + RAW_BYTES) {
                raw_reject(s, RAW_OVERLAP);
                return;
            }
        }
        if (!raw_writable(s, dst[i])) {
            raw_reject(s, RAW_NOT_RAM);
            return;
        }
    }
    /* All four slots preflighted under BQL before any write. One zero pad
     * byte per row. Pair (a,b) => a[7:0], a[11:8]|b[3:0]<<4, b[11:4]. */
    g_autofree uint8_t *frame = g_malloc0(RAW_BYTES);
    for (unsigned y = 0; y < RAW_HEIGHT; y++) {
        for (unsigned x = 0; x < RAW_WIDTH; x += 2) {
            unsigned a = (x * 3 + y * 5 + 0x100) & 0xfff;
            unsigned b = ((x + 1) * 3 + y * 5 + 0x100) & 0xfff;
            unsigned p = y * RAW_STRIDE + x / 2 * 3;
            frame[p] = a;
            frame[p + 1] = (a >> 8) | ((b & 15) << 4);
            frame[p + 2] = b >> 4;
        }
    }
    for (unsigned i = 0; i < 4; i++) {
        if (address_space_write(&s->raw_memory, dst[i], MEMTXATTRS_UNSPECIFIED,
                                frame, RAW_BYTES) != MEMTX_OK) {
            raw_reject(s, RAW_IO);
            return;
        }
    }
    s->raw_accepted++;
    s->raw_bytes += 4 * RAW_BYTES;
    s->raw_reason = RAW_SUCCESS;
    qemu_set_irq(s->raw_complete, 1);
    qemu_set_irq(s->raw_complete, 0);
}

static void raw_realize(DeviceState *dev, Error **errp)
{
    Z72InputConfig *s = Z72_INPUT_CONFIG(dev);
    if (s->z62_layout && !s->raw_root) {
        error_setg(errp, "Z62 functional RAW requires engine-local root");
        return;
    }
    if (s->raw_root) {
        address_space_init(&s->raw_memory, s->raw_root, "z62-functional-raw");
    }
}

static void raw_unrealize(DeviceState *dev)
{
    Z72InputConfig *s = Z72_INPUT_CONFIG(dev);
    if (s->raw_root) {
        address_space_destroy(&s->raw_memory);
    }
}

/* Only enabled Z62 streams carry this new v1 subsection. Legacy/default-off
 * input-config v2 and Z72 migration layout remain unchanged. Destination
 * must use the same functional-raw property, like other machine options. */
static bool raw_vmstate_needed(void *opaque)
{
    Z72InputConfig *s = opaque;
    return s->z62_layout && s->functional_raw;
}

static const VMStateDescription raw_vmstate = {
    .name = TYPE_Z72_INPUT_CONFIG "/functional-raw",
    .version_id = 1,
    .minimum_version_id = 1,
    .needed = raw_vmstate_needed,
    .fields = (const VMStateField[]) {
        VMSTATE_UINT64(raw_accepted, Z72InputConfig),
        VMSTATE_UINT64(raw_rejected, Z72InputConfig),
        VMSTATE_UINT64(raw_bytes, Z72InputConfig),
        VMSTATE_UINT32(raw_reason, Z72InputConfig),
        VMSTATE_BOOL(raw_submit_level, Z72InputConfig),
        VMSTATE_END_OF_LIST()
    },
};
