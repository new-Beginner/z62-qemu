/* SPDX-License-Identifier: GPL-2.0-or-later
 * Private, immutable linear12 view of an actually DMA-completed CW frame.
 * Quantized midpoint reconstruction, not recovery of original low bits.
 * No raw_accepted/raw_stream counters or guest software state are modified.
 */
static int cw_stats_compute(Z62CWTask *task)
{
    if (!task->statistics_bridge) return 0;
    uint32_t w=task->pixels.output_width,h=task->pixels.output_height;
    if (w!=Z62_STATS_RAW_W || h!=Z62_STATS_RAW_H) return -1;
    g_autofree uint8_t *linear16=g_malloc((size_t)w*h*2);
    if (z62_transfer_unpack(&task->transfer,task->packed,task->packed_bytes,w,h,
        task->pixels.output_stride,linear16,(size_t)w*h*2,w*2)!=Z62_TRANSFER_OK) return -1;
    task->statistics_linear=g_malloc0(Z62_STATS_RAW_BYTES);
    Z62CaptureWorkPixelsConfig view={.input_width=w,.input_height=h,.input_stride=w*2,
        .intermediate_width=w,.intermediate_height=h,.output_width=w,.output_height=h,
        .output_stride=Z62_STATS_RAW_STRIDE,.bits=12,.cfa=1};
    return z62_capturework_pixels_pack(&view,linear16,(size_t)w*h*2,
        task->statistics_linear,Z62_STATS_RAW_BYTES)==Z62_CW_PIXELS_OK?0:-1;
}

static void cw_stats_invalidate(Z72InputConfig *s)
{
    if (s->cw_stats.pending) s->cw_stats.invalidated++;
    s->cw_stats.pending=false;
    g_clear_pointer(&s->cw_stats.linear,g_free);
}

static bool cw_stats_ready(Z72InputConfig *s)
{
    return s->cw_stats.pending && s->cw_stats.linear &&
        s->cw_stats.generation==s->cw.generation && s->cw.output_valid;
}

static void cw_stats_publish(Z72InputConfig *s,Z62CWTask *task)
{
    if (!s->cw_stats.enabled) return;
    g_assert(task->statistics_linear && !s->cw_stats.pending);
    g_free(s->cw_stats.linear);
    s->cw_stats.linear=task->statistics_linear; task->statistics_linear=NULL;
    s->cw_stats.pending=true; s->cw_stats.generation=task->generation;
    s->cw_stats.meta=task->lease.meta; s->cw_stats.transfer=task->transfer;
    s->cw_stats.address=task->destination; s->cw_stats.bank=task->bank; s->cw_stats.slot=task->slot;
    s->cw_stats.published++;
}

static void cw_stats_consumed(Z72InputConfig *s)
{
    g_assert(cw_stats_ready(s));
    s->cw_stats.pending=false; s->cw_stats.consumed++;
    s->cw_stats.statistics_slot=s->continuous_index;
}

static char *cw_stats_status(Object *obj,Error **errp)
{
    Z72InputConfig *s=Z72_INPUT_CONFIG(obj);
    return g_strdup_printf("{\"enabled\":%s,\"pending\":%s,\"valid\":%s,"
        "\"published\":%" PRIu64 ",\"consumed\":%" PRIu64 ",\"invalidated\":%" PRIu64 ","
        "\"generation\":%" PRIu64 ",\"epoch\":%" PRIu64 ",\"publication\":%" PRIu64 ","
        "\"frame\":%" PRIu64 ",\"time_ns\":%" PRIu64 ",\"address\":%u,\"bank\":%u,"
        "\"slot\":%u,\"statistics_slot\":%u,\"bits\":%u,\"codec\":%u,"
        "\"view\":\"quantized-midpoint-linear12\",\"guest_encoded_RAW_preserved\":true}",
        s->cw_stats.enabled?"true":"false",s->cw_stats.pending?"true":"false",
        cw_stats_ready(s)?"true":"false",s->cw_stats.published,s->cw_stats.consumed,
        s->cw_stats.invalidated,s->cw_stats.generation,s->cw_stats.meta.epoch,
        s->cw_stats.meta.publication,s->cw_stats.meta.frame,s->cw_stats.meta.time_ns,
        s->cw_stats.address,s->cw_stats.bank,s->cw_stats.slot,s->cw_stats.statistics_slot,
        s->cw_stats.transfer.bits,s->cw_stats.transfer.codec);
}
