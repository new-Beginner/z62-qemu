/* SPDX-License-Identifier: GPL-2.0-or-later
 * Default-off diagnostics. The original bridge is invoked exactly once.
 * PC is the current virtual CPU's candidate PC, not a decoded store address.
 */
static bool statistics_supported(NikonZ72BootConfig *s)
{
    return s->z62_finite_stats && s->z62_card_detect && s->master_role;
}

static bool statistics_enabled(NikonZ72BootConfig *s)
{
    return statistics_supported(s) && s->finite_started &&
        (*boot_config_value(s, 0x20068010) & 0x10);
}

static bool statistics_control_address(hwaddr address)
{
    return (address >= 0x20068000 && address <= 0x20068018 && !(address & 3)) ||
        address == 0x20068100;
}

static void finite_bridge_control(NikonZ72BootConfig *s, hwaddr address, uint32_t value)
{
    bool before = s->finite_started;
    finite_bridge_control_model(s, address, value);
    if (!s->z62_statistics_observe) { return; }
    if (statistics_supported(s) && address == 0x20068100 && (value & 8)) {
        s->statistics_commit_pulses++;
    }
    if (statistics_control_address(address)) {
        unsigned i = s->statistics_control_count++ % 256;
        CPUState *cpu = current_cpu;
        s->statistics_address[i] = address;
        s->statistics_value[i] = value;
        s->statistics_mask[i] = *boot_config_value(s, 0x20068010);
        s->statistics_flags[i] = (before ? 1 : 0) | (s->finite_started ? 2 : 0) |
            (statistics_supported(s) ? 4 : 0) | (statistics_enabled(s) ? 8 : 0) | (cpu ? 16 : 0);
        s->statistics_cpu[i] = cpu ? cpu->cpu_index : -1;
        s->statistics_pc[i] = cpu ? ARM_CPU(cpu)->env.regs[15] : 0;
        s->statistics_time[i] = qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL);
        s->statistics_frame[i] = s->frame_sync_count;
    }
}

static void finite_bridge_frame(NikonZ72BootConfig *s)
{
    if (s->z62_statistics_observe) {
        s->statistics_frame_calls++;
        if (statistics_supported(s)) { s->statistics_frame_pulses++; }
    }
    finite_bridge_frame_model(s);
}

static void statistics_observe_reset(NikonZ72BootConfig *s)
{
    s->statistics_control_count = s->statistics_frame_calls = 0;
    s->statistics_frame_pulses = s->statistics_commit_pulses = 0;
    memset(s->statistics_address, 0, sizeof(s->statistics_address));
    memset(s->statistics_value, 0, sizeof(s->statistics_value));
    memset(s->statistics_mask, 0, sizeof(s->statistics_mask));
    memset(s->statistics_flags, 0, sizeof(s->statistics_flags));
    memset(s->statistics_pc, 0, sizeof(s->statistics_pc));
    memset(s->statistics_cpu, 0, sizeof(s->statistics_cpu));
    memset(s->statistics_time, 0, sizeof(s->statistics_time));
    memset(s->statistics_frame, 0, sizeof(s->statistics_frame));
}

static bool statistics_started_get(Object *obj, Error **errp)
{
    return NIKON_Z72_BOOT_CONFIG(obj)->finite_started;
}
static bool statistics_enable_get(Object *obj, Error **errp)
{
    return statistics_enabled(NIKON_Z72_BOOT_CONFIG(obj));
}
static bool statistics_support_get(Object *obj, Error **errp)
{
    return statistics_supported(NIKON_Z72_BOOT_CONFIG(obj));
}

static char *statistics_trace_get(Object *obj, Error **errp)
{
    NikonZ72BootConfig *s = NIKON_Z72_BOOT_CONFIG(obj);
    GString *json = g_string_new("[");
    uint64_t n = MIN(s->statistics_control_count, 256);
    for (uint64_t offset = 0; offset < n; offset++) {
        uint64_t sequence = s->statistics_control_count - n + offset + 1;
        unsigned i = (sequence - 1) % 256;
        uint32_t flags = s->statistics_flags[i];
        g_string_append_printf(json,
            "%s{\"sequence\":%" PRIu64 ",\"address\":\"0x%08x\",\"value\":\"0x%08x\","
            "\"mask_after\":\"0x%08x\",\"started_before\":%s,\"started_after\":%s,"
            "\"model_supported\":%s,\"model_enable\":%s,\"pc_valid\":%s,"
            "\"pc\":\"0x%08x\",\"cpu\":%d,\"qemu_virtual_ns\":%" PRId64 ",\"frame_count\":%" PRIu64 "}",
            offset ? "," : "", sequence, s->statistics_address[i], s->statistics_value[i],
            s->statistics_mask[i], flags & 1 ? "true" : "false", flags & 2 ? "true" : "false",
            flags & 4 ? "true" : "false", flags & 8 ? "true" : "false", flags & 16 ? "true" : "false",
            s->statistics_pc[i], s->statistics_cpu[i], s->statistics_time[i], s->statistics_frame[i]);
    }
    g_string_append_c(json, ']');
    return g_string_free(json, false);
}

static void statistics_observe_init(Object *obj)
{
    NikonZ72BootConfig *s = NIKON_Z72_BOOT_CONFIG(obj);
    object_property_add_bool(obj, "statistics-model-started", statistics_started_get, NULL);
    object_property_add_bool(obj, "statistics-model-enable", statistics_enable_get, NULL);
    object_property_add_bool(obj, "statistics-model-support", statistics_support_get, NULL);
    object_property_add_str(obj, "statistics-control-trace", statistics_trace_get, NULL);
    object_property_add_uint64_ptr(obj, "statistics-control-count", &s->statistics_control_count, OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(obj, "statistics-frame-calls", &s->statistics_frame_calls, OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(obj, "statistics-frame-pulses", &s->statistics_frame_pulses, OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(obj, "statistics-commit-pulses", &s->statistics_commit_pulses, OBJ_PROP_FLAG_READ);
}
