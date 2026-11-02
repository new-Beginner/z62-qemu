/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Nikon Z6II 1.70 bring-up board, lab 0.4.0.
 * Architecture references: WonderLantern/z6-qemu and JKWTCN/z72-qemu (GPL).
 * No firmware patches or IPC stand-ins. Completion is an explicit experiment.
 * Cortex-A15, CBAR and GIC are execution hypotheses, not silicon identification.
 */
#include "qemu/osdep.h"
#include "qemu/error-report.h"
#include "qapi/error.h"
#include "hw/boards.h"
#include "hw/arm/machines-qom.h"
#include "hw/loader.h"
#include "hw/cpu/a15mpcore.h"
#include "hw/qdev-properties.h"
#include "hw/irq.h"
#include "target/arm/cpu.h"
#include "system/runstate.h"
#include "system/reset.h"
#include "exec/cpu-common.h"
#include "exec/target_page.h"
#include "nikon-z6ii-platform.h"

#define TYPE_NIKON_Z6II_MACHINE MACHINE_TYPE_NAME("nikon-z6ii")
OBJECT_DECLARE_SIMPLE_TYPE(NikonZ6IIMachineState, NIKON_Z6II_MACHINE)
#define Z6II_BASE 0x10020000U
#define Z6II_ROM_SIZE 0x04000000U
#define Z6II_CBAR 0x2c000000U
#define Z6II_VERSION "0.4.0"

typedef struct Z6IIImage {
    const char *role;
    size_t bytes;
    const char *sha256;
    uint32_t data_source;
    uint32_t data_destination;
    uint32_t data_length;
} Z6IIImage;

static const Z6IIImage images[] = {
    { "master", 38750136,
      "7b85aa96ea25d6b23481627313082476619ccb4dd3634a585de4ed896d350071",
      0x123a1c14, 0xc1800000, 0xaedb8 },
    { "slave", 8832192,
      "ed7be55b90024270c9e8227fa2effd66a0eb8f32e96de23e3d1a7a196cdaf676",
      0x1085c054, 0xc1000000, 0x17dc8 },
};

/* Historical v0.3.0 passive subset, retained for platform-config=off.
 * Z6II uses 0x1/0x101 at 0x200300b8/0x2002010c in both roles.
 * Zero reset and the extended synchronous completion remain lab choices. */
static const hwaddr config_addresses[] = {
    0x04264000, 0x04264020, 0x04281028, 0x0428102c,
    0x20020000, 0x20020100, 0x2002010c,
    0x20021004, 0x20021008, 0x2002100c, 0x20021010, 0x20021014,
    0x20022000, 0x20022100, 0x20022408, 0x20022414, 0x20023000,
    0x20030010, 0x20030014, 0x20030018, 0x2003001c, 0x20030020,
    0x20030024, 0x20030030, 0x20030034, 0x20030040, 0x20030044,
    0x20030048, 0x20030050, 0x20030054, 0x20030058, 0x2003005c,
    0x20030060, 0x20030074, 0x20030078, 0x2003007c, 0x20030080,
    0x20030094, 0x20030098, 0x2003009c, 0x200300a0, 0x200300b8,
    0x200300e4, 0x200300e8, 0x200300ec, 0x200300f0,
    0x20030128, 0x2003012c, 0x20030130, 0x20030134,
    0x20030148, 0x2003014c, 0x20030150, 0x20030154,
    0x20030820, 0x20030824, 0x20030828, 0x2003082c,
    0x20030840, 0x20030850, 0x20030910,
};

typedef struct Z6IIConfigBank {
    NikonZ6IIMachineState *machine;
    hwaddr base;
    MemoryRegion region;
} Z6IIConfigBank;

struct NikonZ6IIMachineState {
    MachineState parent_obj;
    char *engine;
    const Z6IIImage *image;
    MemoryRegion rom;
    MemoryRegion boot_sram;
    MemoryRegion initialized_ram;
    MemoryRegion unknown;
    ARMCPU *cpus[2];
    unsigned cpu_count;
    bool faulted;
    bool boot_config;
    bool trace_config;
    bool platform_config;
    bool auto_complete;
    uint32_t blocked_control;
    uint32_t completion_result;
    uint32_t config_values[Z6II_PLATFORM_WORDS];
    Z6IIConfigBank config_banks[2];
};

/* env PC can lag at consecutive MMIO stores. Read unwind data only; never
 * restore/mutate guest state. QEMU 10.2.4 ARM always enables CF_PCREL. */
static uint32_t z6ii_access_pc(CPUState *cpu)
{
    uint32_t pc = ARM_CPU(cpu)->env.regs[15];
    uint64_t data[3];
    if (cpu_unwind_state_data(cpu, cpu->mem_io_pc, data)) {
        pc = (pc & TARGET_PAGE_MASK) | data[0];
    }
    return pc;
}

static void z6ii_unknown(NikonZ6IIMachineState *s, hwaddr address,
                         unsigned size, bool write, uint64_t value)
{
    if (!current_cpu || s->faulted) {
        return; /* Debugger probes return MEMTX_ERROR, without killing a VM. */
    }
    s->faulted = true;
    ARMCPU *cpu = ARM_CPU(current_cpu);
    fprintf(stderr,
            "Z6II_EVENT {\"event\":\"unmodeled-mmio\",\"engine\":\"%s\","
            "\"access\":\"%s\",\"address\":%" PRIu64 ",\"size\":%u,"
            "\"value\":%" PRIu64 ",\"pc\":%u,\"cpu\":%d,\"cpsr\":%u,"
            "\"registers\":[",
            s->image->role, write ? "write" : "read", (uint64_t)address,
            size, value, z6ii_access_pc(current_cpu), current_cpu->cpu_index,
            cpsr_read(&cpu->env));
    for (unsigned n = 0; n < 16; n++) {
        fprintf(stderr, "%s%u", n ? "," : "", cpu->env.regs[n]);
    }
    fprintf(stderr, "],\"response_fabricated\":false}\n");
    fflush(stderr);
    qemu_system_shutdown_request_with_code(SHUTDOWN_CAUSE_GUEST_PANIC, 2);
}

static MemTxResult z6ii_read(void *opaque, hwaddr address, uint64_t *value,
                             unsigned size, MemTxAttrs attrs)
{
    *value = 0; /* Transaction is rejected; this is not a valid device reply. */
    z6ii_unknown(opaque, address, size, false, 0);
    return MEMTX_ERROR;
}

static MemTxResult z6ii_write(void *opaque, hwaddr address, uint64_t value,
                              unsigned size, MemTxAttrs attrs)
{
    z6ii_unknown(opaque, address, size, true, value);
    return MEMTX_ERROR;
}

static const MemoryRegionOps z6ii_unknown_ops = {
    .read_with_attrs = z6ii_read,
    .write_with_attrs = z6ii_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid = { .min_access_size = 1, .max_access_size = 8 },
    .impl = { .min_access_size = 1, .max_access_size = 8 },
};

static int z6ii_config_index(NikonZ6IIMachineState *s, hwaddr address,
                              unsigned size)
{
    if (size != 4 || (address & 3)) {
        return -1;
    }
    if (!s->platform_config) {
        bool passive = false;
        for (unsigned i = 0; i < ARRAY_SIZE(config_addresses); i++) {
            passive |= config_addresses[i] == address;
        }
        if (!passive) {
            return -1;
        }
    }
    unsigned extra = 0;
    if (address >= 0x20040000 && address < 0x20060000) {
        address -= 0x20000;
        extra = ARRAY_SIZE(platform_addresses) - 4;
    }
    for (unsigned i = 0; i < ARRAY_SIZE(platform_addresses); i++) {
        if (platform_addresses[i] == address) {
            return i + extra;
        }
    }
    return -1;
}

static void z6ii_config_trace(NikonZ6IIMachineState *s, hwaddr address,
                              bool write, uint32_t value)
{
    if (s->trace_config && current_cpu) {
        fprintf(stderr,
                "Z6II_CONFIG {\"access\":\"%s\",\"address\":%" PRIu64
                ",\"value\":%u,\"size\":4,\"pc\":%u}\n",
                write ? "write" : "read", (uint64_t)address, value,
                z6ii_access_pc(current_cpu));
    }
}

static MemTxResult z6ii_config_read(void *opaque, hwaddr offset, uint64_t *value,
                                    unsigned size, MemTxAttrs attrs)
{
    Z6IIConfigBank *bank = opaque;
    NikonZ6IIMachineState *s = bank->machine;
    hwaddr address = bank->base + offset;
    int index = z6ii_config_index(s, address, size);
    *value = 0;
    if (index < 0) {
        z6ii_unknown(s, address, size, false, 0);
        return MEMTX_ERROR;
    }
    *value = s->platform_config && (address == 0x2003016c || address == 0x2005016c)
             ? s->completion_result : s->config_values[index];
    z6ii_config_trace(s, address, false, *value);
    return MEMTX_OK;
}

static MemTxResult z6ii_config_write(void *opaque, hwaddr offset, uint64_t value,
                                     unsigned size, MemTxAttrs attrs)
{
    Z6IIConfigBank *bank = opaque;
    NikonZ6IIMachineState *s = bank->machine;
    hwaddr address = bank->base + offset;
    int index = z6ii_config_index(s, address, size);
    if (index < 0) {
        z6ii_unknown(s, address, size, true, value);
        return MEMTX_ERROR;
    }
    z6ii_config_trace(s, address, true, value);
    if (s->platform_config) {
        /* Readonly experimental result words; host injection is a property. */
        if (address == 0x2003016c || address == 0x2005016c) {
            return MEMTX_OK;
        }
        hwaddr channel = address >= 0x20040000 ? 0x20000 : 0;
        for (unsigned i = 0; i < ARRAY_SIZE(completions); i++) {
            const Z6IICompletion *c = &completions[i];
            if (address == c->status + channel) {
                s->config_values[index] &= ~(uint32_t)value; /* W1C */
                return MEMTX_OK;
            }
            if (address == c->control + channel) {
                bool valid = c->max_phase
                    ? ((value & 0xffff) == c->command &&
                       (value >> 16) <= c->max_phase)
                    : value == c->command;
                int status = z6ii_config_index(s, c->status + channel, 4);
                assert(status >= 0);
                s->config_values[status] = s->auto_complete && valid &&
                                          s->blocked_control != address;
            }
        }
    }
    s->config_values[index] = value;
    return MEMTX_OK;
}

static const MemoryRegionOps z6ii_config_ops = {
    .read_with_attrs = z6ii_config_read,
    .write_with_attrs = z6ii_config_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    /* Route widths/alignment to the callback so invalid accesses get the
     * same strict diagnostic as unassigned holes, not a silent zero reply. */
    .valid = { .min_access_size = 1, .max_access_size = 8, .unaligned = true },
    .impl = { .min_access_size = 1, .max_access_size = 8, .unaligned = true },
};

static bool z6ii_get_boot_config(Object *obj, Error **errp)
{
    return NIKON_Z6II_MACHINE(obj)->boot_config;
}

static void z6ii_set_boot_config(Object *obj, bool value, Error **errp)
{
    NIKON_Z6II_MACHINE(obj)->boot_config = value;
}

static bool z6ii_get_trace_config(Object *obj, Error **errp)
{
    return NIKON_Z6II_MACHINE(obj)->trace_config;
}

static void z6ii_set_trace_config(Object *obj, bool value, Error **errp)
{
    NIKON_Z6II_MACHINE(obj)->trace_config = value;
}

static bool z6ii_get_platform_config(Object *obj, Error **errp)
{
    return NIKON_Z6II_MACHINE(obj)->platform_config;
}

static void z6ii_set_platform_config(Object *obj, bool value, Error **errp)
{
    NIKON_Z6II_MACHINE(obj)->platform_config = value;
}

static bool z6ii_get_auto_complete(Object *obj, Error **errp)
{
    return NIKON_Z6II_MACHINE(obj)->auto_complete;
}

static void z6ii_set_auto_complete(Object *obj, bool value, Error **errp)
{
    NIKON_Z6II_MACHINE(obj)->auto_complete = value;
}

static void z6ii_instance_init(Object *obj)
{
    NikonZ6IIMachineState *s = NIKON_Z6II_MACHINE(obj);
    s->boot_config = true;
    s->platform_config = true;
    s->auto_complete = true;
    object_property_add_uint32_ptr(obj, "blocked-control", &s->blocked_control,
                                   OBJ_PROP_FLAG_READWRITE);
    object_property_add_uint32_ptr(obj, "completion-result", &s->completion_result,
                                   OBJ_PROP_FLAG_READWRITE);
}

static void z6ii_reset(void *opaque)
{
    NikonZ6IIMachineState *s = opaque;
    s->faulted = false;
    memset(s->config_values, 0, sizeof(s->config_values));
    for (unsigned n = 0; n < s->cpu_count; n++) {
        cpu_set_pc(CPU(s->cpus[n]), Z6II_BASE);
    }
}

static char *z6ii_get_engine(Object *obj, Error **errp)
{
    NikonZ6IIMachineState *s = NIKON_Z6II_MACHINE(obj);
    return g_strdup(s->engine ? s->engine : "master");
}

static void z6ii_set_engine(Object *obj, const char *value, Error **errp)
{
    NikonZ6IIMachineState *s = NIKON_Z6II_MACHINE(obj);
    if (strcmp(value, "master") && strcmp(value, "slave")) {
        error_setg(errp, "engine must be master or slave; dual chips are not -smp 2");
        return;
    }
    g_free(s->engine);
    s->engine = g_strdup(value);
}

static void z6ii_init(MachineState *machine)
{
    NikonZ6IIMachineState *s = NIKON_Z6II_MACHINE(machine);
    const char *role = s->engine ? s->engine : "master";
    s->image = &images[!strcmp(role, "slave")];
    const Z6IIImage *image = s->image;
    if (s->blocked_control) {
        bool known = false;
        for (unsigned i = 0; i < ARRAY_SIZE(completions); i++) {
            known |= s->blocked_control == completions[i].control ||
                     s->blocked_control == completions[i].control + 0x20000;
        }
        if (!known) {
            error_report("blocked-control must be zero or an observed command address");
            exit(1);
        }
    }
    g_autofree gchar *payload = NULL;
    g_autofree gchar *sha256 = NULL;
    gsize length = 0;
    g_autoptr(GError) error = NULL;

    if (!machine->firmware ||
        !g_file_get_contents(machine->firmware, &payload, &length, &error)) {
        error_report("Z6II needs -bios <extracted %s 1.70 payload>: %s",
                     role, error ? error->message : "no payload supplied");
        exit(1);
    }
    sha256 = g_compute_checksum_for_data(G_CHECKSUM_SHA256,
                                        (const guchar *)payload, length);
    if (length != image->bytes || strcmp(sha256, image->sha256)) {
        error_report("Z6II %s payload SHA-256/length mismatch; original image required", role);
        exit(1);
    }
    MemoryRegion *sysmem = get_system_memory();
    memory_region_init_io(&s->unknown, OBJECT(machine), &z6ii_unknown_ops,
                          s, "z6ii-unmodeled", UINT64_C(0x100000000));
    memory_region_add_subregion_overlap(sysmem, 0, &s->unknown, -100);
    if (s->boot_config) {
        const hwaddr bases[] = { 0x04200000, 0x20020000 };
        const uint64_t sizes[] = { 0x100000, 0x40000 };
        for (unsigned i = 0; i < ARRAY_SIZE(s->config_banks); i++) {
            Z6IIConfigBank *bank = &s->config_banks[i];
            bank->machine = s;
            bank->base = bases[i];
            memory_region_init_io(&bank->region, OBJECT(machine),
                                  &z6ii_config_ops, bank, "z6ii-experimental-config",
                                  sizes[i]);
            memory_region_add_subregion(sysmem, bases[i], &bank->region);
        }
    }
    /* 64 MiB is a host mapping envelope, NOT identified flash capacity.
     * The master payload exceeds the donor Z6 board's 32 MiB envelope. */
    memory_region_init_rom(&s->rom, NULL, "z6ii-payload-rom",
                           Z6II_ROM_SIZE, &error_fatal);
    memory_region_add_subregion(sysmem, Z6II_BASE, &s->rom);
    rom_add_blob_fixed("z6ii-original-payload", payload, length, Z6II_BASE);
    /* Original reset code uses SP 0x04008f00 and mailbox 0x04008ffc. */
    memory_region_init_ram(&s->boot_sram, NULL, "z6ii-boot-sram",
                           0x1000, &error_fatal);
    memory_region_add_subregion(sysmem, 0x04008000, &s->boot_sram);
    /* Only the observed initialized-data destination is backed here.
     * Do not pre-copy it: original guest startup must perform the copy.
     * BSS, heap, ISP buffers and peer-chip windows remain unmodeled. */
    memory_region_init_ram(&s->initialized_ram, NULL,
                           "z6ii-initialized-data-ram",
                           (image->data_length + 0xfff) & ~0xfffU, &error_fatal);
    memory_region_add_subregion(sysmem, image->data_destination,
                                &s->initialized_ram);
    s->cpu_count = machine->smp.cpus;
    for (unsigned n = 0; n < s->cpu_count; n++) {
        Object *obj = object_new(machine->cpu_type);
        s->cpus[n] = ARM_CPU(obj);
        object_property_set_int(obj, "reset-cbar", Z6II_CBAR, &error_fatal);
        object_property_set_bool(obj, "has_el2", false, &error_fatal);
        object_property_set_int(obj, "cntfrq", 48000000, &error_fatal);
        qdev_realize(DEVICE(obj), NULL, &error_fatal);
    }
    DeviceState *priv = qdev_new(TYPE_A15MPCORE_PRIV);
    A15MPPrivState *a15 = A15MPCORE_PRIV(priv);
    qdev_prop_set_uint32(DEVICE(&a15->gic), "revision", 1);
    qdev_prop_set_uint32(priv, "num-cpu", s->cpu_count);
    qdev_prop_set_uint32(priv, "num-irq", 256);
    SysBusDevice *bus = SYS_BUS_DEVICE(priv);
    sysbus_realize_and_unref(bus, &error_fatal);
    sysbus_mmio_map(bus, 0, Z6II_CBAR);
    for (unsigned n = 0; n < s->cpu_count; n++) {
        DeviceState *cpu = DEVICE(s->cpus[n]);
        sysbus_connect_irq(bus, n, qdev_get_gpio_in(cpu, ARM_CPU_IRQ));
        sysbus_connect_irq(bus, n + s->cpu_count,
                           qdev_get_gpio_in(cpu, ARM_CPU_FIQ));
        sysbus_connect_irq(bus, n + 2 * s->cpu_count,
                           qdev_get_gpio_in(cpu, ARM_CPU_VIRQ));
        sysbus_connect_irq(bus, n + 3 * s->cpu_count,
                           qdev_get_gpio_in(cpu, ARM_CPU_VFIQ));
    }
    qemu_register_reset(z6ii_reset, s);
    fprintf(stderr,
            "Z6II_BOOT {\"lab_version\":\"%s\",\"engine\":\"%s\","
            "\"payload_sha256\":\"%s\",\"cores_within_one_engine\":%u,"
            "\"entry\":%u,\"cpu_model_hypothesis\":true,"
            "\"boot_config_enabled\":%s,\"config_reset_is_hypothesis\":true,"
            "\"config_word_count\":%zu,\"completion_feedback_modeled\":%s,"
            "\"completion_model_is_hypothesis\":true,\"auto_complete\":%s,"
            "\"blocked_control\":%u,\"completion_result\":%u,"
            "\"dual_chip_ipc_modeled\":false,\"menu_reached\":false}\n",
            Z6II_VERSION, role, sha256, s->cpu_count, Z6II_BASE,
            s->boot_config ? "true" : "false",
            s->boot_config ? (s->platform_config ? Z6II_PLATFORM_WORDS : ARRAY_SIZE(config_addresses)) : 0,
            s->boot_config && s->platform_config ? "true" : "false",
            s->auto_complete ? "true" : "false", s->blocked_control, s->completion_result);
}

static void z6ii_class_init(ObjectClass *oc, const void *data)
{
    MachineClass *mc = MACHINE_CLASS(oc);
    mc->desc = "Nikon Z6II 1.70 strict bring-up board (lab 0.4.0, no MENU yet)";
    mc->init = z6ii_init;
    mc->default_cpu_type = ARM_CPU_TYPE_NAME("cortex-a15");
    mc->min_cpus = 1;
    mc->default_cpus = 1;
    mc->max_cpus = 2; /* Cores inside ONE selected engine, not two EXPEED chips. */
    mc->default_ram_size = 0;
    object_class_property_add_str(oc, "engine", z6ii_get_engine, z6ii_set_engine);
    object_class_property_set_description(oc, "engine", "Z6II payload role: master or slave");
    object_class_property_add_bool(oc, "boot-config", z6ii_get_boot_config,
                                   z6ii_set_boot_config);
    object_class_property_set_description(oc, "boot-config",
        "Enable bounded experimental configuration model (default on)");
    object_class_property_add_bool(oc, "trace-config", z6ii_get_trace_config,
                                   z6ii_set_trace_config);
    object_class_property_set_description(oc, "trace-config",
        "Log successful guest configuration accesses (default off)");
    object_class_property_add_bool(oc, "platform-config", z6ii_get_platform_config,
                                   z6ii_set_platform_config);
    object_class_property_set_description(oc, "platform-config",
        "Enable 346-word dual-channel experiment; off restores v0.3.0 (default on)");
    object_class_property_add_bool(oc, "auto-complete", z6ii_get_auto_complete,
                                   z6ii_set_auto_complete);
    object_class_property_set_description(oc, "auto-complete",
        "Synchronous command completion hypothesis; off runs original timeouts");
}

static const TypeInfo z6ii_type = {
    .name = TYPE_NIKON_Z6II_MACHINE,
    .parent = TYPE_MACHINE,
    .instance_size = sizeof(NikonZ6IIMachineState),
    .class_init = z6ii_class_init,
    .instance_init = z6ii_instance_init,
    .interfaces = arm_machine_interfaces,
};

static void z6ii_register_types(void)
{
    type_register_static(&z6ii_type);
}
type_init(z6ii_register_types)
