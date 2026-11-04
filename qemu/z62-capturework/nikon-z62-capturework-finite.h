/* SPDX-License-Identifier: GPL-2.0-or-later
 * Independent retained-image source for the existing finite sampling model.
 * Source epoch/publication/frame/time stay fixed throughout a batch. The 61
 * actual scalar sample DMAs are not 61 new RAW/MAIN acquisitions. No fallback
 * pixels, old RAW counter increments or guest-software state writes.
 */
static void cw_finite_capture(Z72InputConfig *s,Z62CWTask *task)
{
    Z62CWFinite *f=&s->cw_finite;
    if (!f->enabled) return;
    g_assert(task->statistics_linear);
    uint8_t *view=g_memdup2(task->statistics_linear,RAW_BYTES);
    g_free(f->linear);f->linear=view;f->valid=true;
    f->meta=task->lease.meta;f->transfer=task->transfer;
    f->address=task->destination;f->bank=task->bank;f->slot=task->slot;
    f->source_cw_generation=task->generation;f->captured++;
}

static void cw_finite_select(Z72InputConfig *s)
{
    if (!s->cw_finite.enabled) return;
    s->cw_finite.batch_meta=s->cw_finite.meta;
    s->cw_finite.batch_serial=s->cw_finite.captured;
    s->cw_finite.batches_prepared++;
}

static bool cw_finite_overlap(Z72InputConfig *s,hwaddr address,uint64_t bytes)
{
    hwaddr raw_offset,destination_offset,raw_span=RAW_BYTES,destination_span=bytes;
    MemoryRegion *raw=address_space_translate(&s->raw_memory,s->cw_finite.address,
        &raw_offset,&raw_span,false,MEMTXATTRS_UNSPECIFIED);
    MemoryRegion *destination=address_space_translate(&s->raw_memory,address,
        &destination_offset,&destination_span,true,MEMTXATTRS_UNSPECIFIED);
    return raw && raw==destination && destination_offset<raw_offset+RAW_BYTES && raw_offset<destination_offset+bytes;
}

static void cw_finite_reset(Z72InputConfig *s)
{
    bool enabled=s->cw_finite.enabled;
    g_free(s->cw_finite.linear);memset(&s->cw_finite,0,sizeof(s->cw_finite));s->cw_finite.enabled=enabled;
}

static char *cw_finite_status(Object *obj,Error **errp)
{
    Z72InputConfig *s=Z72_INPUT_CONFIG(obj);Z62CWFinite *f=&s->cw_finite;
    return g_strdup_printf("{\"enabled\":%s,\"valid\":%s,\"captured\":%" PRIu64 ","
        "\"source_CW_generation\":%" PRIu64 ",\"batches_prepared\":%" PRIu64 ","
        "\"batch_source_serial\":%" PRIu64 ",\"source_address\":%u,\"source_bank\":%u,\"source_slot\":%u,"
        "\"latest_publication\":%" PRIu64 ",\"batch_epoch\":%" PRIu64 ",\"batch_publication\":%" PRIu64 ","
        "\"batch_frame\":%" PRIu64 ",\"batch_time_ns\":%" PRIu64 ",\"finite_frames\":%" PRIu64 ","
        "\"mode\":\"finite-samples-of-one-retained-quantized-linear12-frame\",\"new_RAW_acquisitions\":false}",
        f->enabled?"true":"false",f->valid?"true":"false",f->captured,f->source_cw_generation,
        f->batches_prepared,f->batch_serial,f->address,f->bank,f->slot,f->meta.publication,
        f->batch_meta.epoch,f->batch_meta.publication,f->batch_meta.frame,f->batch_meta.time_ns,s->finite_frames);
}
