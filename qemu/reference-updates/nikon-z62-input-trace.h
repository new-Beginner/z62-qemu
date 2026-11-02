/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Adapted from JKWTCN/z72-qemu 6a8d5f4. Diagnostic only, no guest writes.
 * Fix the upstream short-ring origin; use a 64-bit count and reset it.
 * Include after NikonZ72BootConfig is defined. */
static void boot_config_trace(NikonZ72BootConfig *s, hwaddr address,
                              uint32_t value, bool is_write)
{
    if (!s->input_trace || address < 0x20060000 || address >= 0x20070000) {
        return;
    }
    unsigned slot = s->input_trace_count % 256;
    s->input_trace_addresses[slot] = address;
    s->input_trace_values[slot] = value;
    s->input_trace_writes[slot] = is_write;
    s->input_trace_count++;
}

static char *boot_config_input_trace_get(Object *obj, Error **errp)
{
    NikonZ72BootConfig *s = NIKON_Z72_BOOT_CONFIG(obj);
    uint64_t total = s->input_trace_count;
    unsigned kept = total < 256 ? total : 256;
    unsigned first = total < 256 ? 0 : total % 256;
    GString *text = g_string_sized_new(kept * 19 + 1);
    for (unsigned i = 0; i < kept; i++) {
        unsigned slot = (first + i) % 256;
        g_string_append_printf(text, "%08x:%08x%c",
                               s->input_trace_addresses[slot],
                               s->input_trace_values[slot],
                               s->input_trace_writes[slot] ? 'w' : 'r');
        if (i + 1 < kept) {
            g_string_append_c(text, ',');
        }
    }
    return g_string_free(text, false);
}
