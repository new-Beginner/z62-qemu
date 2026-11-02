/* SPDX-License-Identifier: GPL-2.0-or-later
 * Include after the frozen preview RAM helpers in the generated r47 tree.
 */
#include "nikon-z62-preview-results-profile.h"

static bool preview_results_pending(NikonZ72BootConfig *s)
{
    return s->z62_preview_results &&
           (ldl_le_p(s->transfer_table + 0x1c) & Z62_PREVIEW_RESULTS_MASK);
}

static bool preview_results_prepare(NikonZ72BootConfig *s,
                                    const uint32_t *widths, const uint32_t *heights)
{
    static const unsigned offsets[] = {0x9e0, 0x940, 0xba0};
    uint8_t parameters[160];
    uint32_t mask = 0;

    if (!s->z62_preview_results) {
        return true;
    }
    for (unsigned i = 0; i < G_N_ELEMENTS(offsets); i++) {
        const uint32_t *registers = &s->preview_core[offsets[i] / 4];
        uint32_t pointer = registers[4];
        if ((pointer & 3) || !preview_ram(s, pointer, sizeof(parameters), false) ||
            address_space_read(&s->preview_memory, pointer, MEMTXATTRS_UNSPECIFIED,
                               parameters, sizeof(parameters)) != MEMTX_OK) {
            return false;
        }
        mask |= z62_preview_result_mask(i, widths[i], heights[i], registers, parameters);
    }
    /* This functional profile processes all three outputs as one bounded group. */
    return mask == Z62_PREVIEW_RESULTS_MASK;
}

static void preview_results_finish(NikonZ72BootConfig *s)
{
    if (s->z62_preview_results) {
        /* Called only after all four RAW reads and twelve NV12 writes succeed. */
        stl_le_p(s->transfer_table + 0x1c,
                 ldl_le_p(s->transfer_table + 0x1c) | Z62_PREVIEW_RESULTS_MASK);
        s->preview_result_batches++;
        s->preview_result_units += 3;
    }
}

static void preview_results_reset(NikonZ72BootConfig *s)
{
    s->preview_result_batches = s->preview_result_units = 0;
    s->preview_result_rejected = s->preview_result_blocked = 0;
}

static void preview_results_qom_init(Object *obj)
{
    NikonZ72BootConfig *s = NIKON_Z72_BOOT_CONFIG(obj);
    object_property_add_uint64_ptr(obj, "preview-result-batches", &s->preview_result_batches,
                                   OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(obj, "preview-result-units", &s->preview_result_units,
                                   OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(obj, "preview-result-rejected", &s->preview_result_rejected,
                                   OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(obj, "preview-result-blocked", &s->preview_result_blocked,
                                   OBJ_PROP_FLAG_READ);
}
