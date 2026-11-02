/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Transaction-linked functional hypothesis, NOT recovered silicon timing.
 * Only the engine-local RAW DMA success wire drives this input on the board.
 * No clock, submit, configuration write, software event or guest-state fixup. */
enum { TX_RESET, TX_DISABLED, TX_MODE, TX_UNARMED, TX_LATCHED, TX_COALESCED };

static char *transaction_reason(Object *obj, Error **errp)
{
    Z62SensorConfig *s = Z62_SENSOR_CONFIG(obj);
    static const char *const names[] = {
        "reset", "disabled", "mode-mismatch", "unarmed-mask", "latched", "coalesced"
    };
    return g_strdup(s->transaction_reason < G_N_ELEMENTS(names) ?
                    names[s->transaction_reason] : "unknown");
}

static void sensor_raw_dma_complete(void *opaque, int line, int level)
{
    Z62SensorConfig *s = opaque;
    bool edge = level && !s->raw_dma_level;
    s->raw_dma_level = level != 0;
    if (!edge) {
        return;
    }
    s->raw_source_events++;
    if (!s->functional_raw_completion) {
        s->raw_ignored++;
        s->transaction_reason = TX_DISABLED;
        return;
    }
    if (!sensor_mode2_configured(s)) {
        s->raw_ignored++;
        s->transaction_reason = TX_MODE;
        return;
    }
    /* Consumer armed means the existing IRQ92 status bit1 mask, not the
     * distinct mode2 sync-handshake arm input. Same predicate as frame-end. */
    if (!(WORD(s, 0x150c) & 2)) {
        s->raw_ignored++;
        s->transaction_reason = TX_UNARMED;
        return;
    }
    if (WORD(s, 0x1508) & 2) {
        s->raw_coalesced++;
        s->transaction_reason = TX_COALESCED;
        return; /* Preserve pending level, never manufacture an IRQ edge. */
    }
    WORD(s, 0x1508) |= 2;
    s->raw_completions++;
    s->transaction_reason = TX_LATCHED;
    sensor_update_irqs(s);
}

static void transaction_realize(DeviceState *dev, Error **errp)
{
    Z62SensorConfig *s = Z62_SENSOR_CONFIG(dev);
    if (s->functional_raw_completion && s->laboratory_frame_completion) {
        error_setg(errp, "functional-raw-completion conflicts with laboratory-frame-completion");
    }
}

static bool transaction_needed(void *opaque)
{
    return Z62_SENSOR_CONFIG(opaque)->functional_raw_completion;
}

static int transaction_post_load(void *opaque, int version)
{
    Z62SensorConfig *s = opaque;
    /* Reject an enabled source stream sent to a disabled/mismatched peer. */
    if (!s->functional_raw_completion || s->laboratory_frame_completion) {
        return -EINVAL;
    }
    sensor_update_irqs(s);
    return 0;
}

/* Base sensor VMState v6 is unchanged. Enabled peers use this v1 subsection;
 * require matching properties. Disabled-source diagnostics are not migrated. */
static const VMStateDescription transaction_vmstate = {
    .name = TYPE_Z62_SENSOR_CONFIG "/raw-transaction",
    .version_id = 1,
    .minimum_version_id = 1,
    .needed = transaction_needed,
    .post_load = transaction_post_load,
    .fields = (const VMStateField[]) {
        VMSTATE_BOOL(raw_dma_level, Z62SensorConfig),
        VMSTATE_UINT64(raw_source_events, Z62SensorConfig),
        VMSTATE_UINT64(raw_completions, Z62SensorConfig),
        VMSTATE_UINT64(raw_ignored, Z62SensorConfig),
        VMSTATE_UINT64(raw_coalesced, Z62SensorConfig),
        VMSTATE_UINT32(transaction_reason, Z62SensorConfig),
        VMSTATE_END_OF_LIST()
    },
};
