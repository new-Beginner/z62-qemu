/* SPDX-License-Identifier: GPL-2.0-or-later
 * Explicit C inline readout of a supplied MAIN/linear16 view. Not physical
 * CMOS timing, full SDES/EX protocol or RAW DMA. Only all-row data consumption
 * may publish the existing functional sensor completion input. No guest RAM,
 * software events, RAW acquisition counters or substitute pixels are written.
 */
static bool input_readout_eligible(Z72InputConfig *s)
{
    Z62CaptureWork *c=&s->cw;
    const uint32_t *g=c->profile.geometry;
    return s->input_readout.enabled && c->enabled && !c->stopping &&
        c->valid[0] && c->valid[1] && !c->profile.correction &&
        !(c->held&1) && (c->allowed&c->running&1) && !(c->running&0x20c) &&
        g[0]==(136u<<16) && g[1]==(2020u<<16) &&
        g[2]==g[0] && g[3]==g[1] && g[4]==0x11;
}

static void input_readout_cancel(Z72InputConfig *s)
{
    Z62InputReadout *r=&s->input_readout;
    timer_del(r->timer);
    if (r->pending) r->cancelled++;
    r->pending=false;
    z62_main_source_stop(&r->source);
}

static void input_readout_control(Z72InputConfig *s)
{
    Z62InputReadout *r=&s->input_readout;
    if (r->pending && (!input_readout_eligible(s) || r->generation!=s->cw.generation))
        input_readout_cancel(s);
}

static void input_readout_tick(void *opaque)
{
    Z72InputConfig *s=opaque;Z62InputReadout *r=&s->input_readout;
    if (!r->pending) return;
    if (!input_readout_eligible(s) || r->generation!=s->cw.generation) {
        input_readout_cancel(s); return;
    }
    uint64_t sum=0,hash=UINT64_C(14695981039346656037),bytes=0;
    for (unsigned y=0;y<r->lease.meta.height;y++) {
        const uint8_t *row=r->lease.pixels+(size_t)y*r->lease.meta.stride;
        for (unsigned x=0;x<r->lease.meta.width;x++) {
            sum+=row[2*x]|((uint16_t)row[2*x+1]<<8);
            for (unsigned b=0;b<2;b++) { hash^=row[2*x+b];hash*=UINT64_C(1099511628211); }
        }
        bytes+=2*r->lease.meta.width;
    }
    r->output=r->lease.meta;r->sum=sum;r->hash=hash;r->bytes+=bytes;
    r->last_rows=r->lease.meta.height;r->last_bytes=bytes;r->completed++;
    g_assert(z62_main_source_release(&r->source,&r->lease)==Z62_MAIN_OK);
    r->pending=false;
    /* Release ownership before a real consumer can synchronously stop/reset. */
    object_ref(OBJECT(s));qemu_irq_pulse(r->complete);object_unref(OBJECT(s));
}

static void input_readout_file(Object *obj,const char *path,Error **errp)
{
    Z72InputConfig *s=Z72_INPUT_CONFIG(obj);Z62InputReadout *r=&s->input_readout;
    GStatBuf info;gchar *data=NULL;gsize size=0;GError *error=NULL;Z62MainMetadata meta;
    if (!input_readout_eligible(s) || r->pending || strlen(path)>4096 ||
        !g_str_is_ascii(path) || !g_path_is_absolute(path) || path[0]=='\\' ||
        g_stat(path,&info) || !S_ISREG(info.st_mode) || info.st_size<96 || info.st_size>96+4096*136) {
        r->rejected++;error_setg(errp,"C inline readout requires idle committed 2020x136 profile and ordinary MAIN file");return;
    }
    if (!g_file_get_contents(path,&data,&size,&error)) {
        r->rejected++;error_setg(errp,"Cannot read explicit input: %s",error->message);g_error_free(error);return;
    }
    Z62MainResult why=z62_main_parse((uint8_t *)data,size,&meta);
    if (why!=Z62_MAIN_OK || meta.width!=2020 || meta.height!=136 || meta.stride>4096) {
        g_free(data);r->rejected++;error_setg(errp,"C inline readout MAIN geometry/CRC invalid");return;
    }
    if (!r->source.pixels) {
        uint8_t *memory=g_malloc(4096*136);
        g_assert(z62_main_source_init(&r->source,memory,4096*136));
    }
    why=z62_main_source_publish(&r->source,(uint8_t *)data,size);g_free(data);
    if (why!=Z62_MAIN_OK) {r->rejected++;error_setg(errp,"C inline readout source ownership/sequence invalid");return;}
    g_assert(z62_main_source_start(&r->source)==Z62_MAIN_OK);
    g_assert(z62_main_source_begin(&r->source,&r->lease)==Z62_MAIN_OK);
    r->generation=s->cw.generation;r->pending=true;r->accepted++;
    /* Declared C transport latency, not a recovered sensor timing constant. */
    timer_mod(r->timer,qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL)+1000000);
}

static char *input_readout_status(Object *obj,Error **errp)
{
    Z72InputConfig *s=Z72_INPUT_CONFIG(obj);Z62InputReadout *r=&s->input_readout;
    return g_strdup_printf("{\"enabled\":%s,\"eligible\":%s,\"pending\":%s,"
        "\"accepted\":%" PRIu64 ",\"completed\":%" PRIu64 ",\"cancelled\":%" PRIu64 ","
        "\"rejected\":%" PRIu64 ",\"bytes\":%" PRIu64 ",\"last_bytes\":%" PRIu64 ","
        "\"rows\":%u,\"sum_u16\":%" PRIu64 ",\"fnv1a64\":%" PRIu64 ","
        "\"epoch\":%" PRIu64 ",\"publication\":%" PRIu64 ",\"frame\":%" PRIu64 ","
        "\"time_ns\":%" PRIu64 ",\"physical_sensor_equivalence\":false,\"guest_RAW_DMA\":false}",
        r->enabled?"true":"false",input_readout_eligible(s)?"true":"false",r->pending?"true":"false",
        r->accepted,r->completed,r->cancelled,r->rejected,r->bytes,r->last_bytes,r->last_rows,r->sum,r->hash,
        r->output.epoch,r->output.publication,r->output.frame,r->output.time_ns);
}

static void input_readout_reset(Z72InputConfig *s)
{
    Z62InputReadout *r=&s->input_readout;input_readout_cancel(s);
    g_clear_pointer(&r->source.pixels,g_free);memset(&r->source,0,sizeof(r->source));
    memset(&r->lease,0,sizeof(r->lease));memset(&r->output,0,sizeof(r->output));
    r->accepted=r->completed=r->cancelled=r->rejected=r->bytes=r->sum=r->hash=r->last_bytes=0;
    r->last_rows=0;qemu_set_irq(r->complete,0);
}
