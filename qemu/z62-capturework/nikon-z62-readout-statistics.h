/* SPDX-License-Identifier: GPL-2.0-or-later
 * C reference input -> finite statistics. No Nikon metering/PDAF claim.
 * Only a completely consumed, owned 2020x136 linear16 input supplies the
 * retained 30x12 LE-u16 mean plane. A finite batch freezes its data/identity.
 */
static void input_readout_cancel(Z72InputConfig *s);

static bool input_statistics_phase(Z72InputConfig *s)
{
    Z62CaptureWork *c=&s->cw;const uint32_t *g=c->profile.geometry;
    return s->input_readout.stats_enabled && s->input_readout.enabled &&
        s->functional_finite_stats && s->finite_enabled && c->enabled && !c->stopping &&
        c->valid[0] && c->valid[1] && !c->profile.correction &&
        g[0]==(136u<<16) && g[1]==(2020u<<16) && g[2]==g[0] && g[3]==g[1] && g[4]==0x11;
}

static bool input_statistics_profile(Z72InputConfig *s)
{
    const uint32_t *r=s->registers;
    return input_statistics_phase(s) && r[0x2514/4]==3 && r[0x2518/4]==1 && !r[0x2524/4] &&
        !(r[0x253c/4]&~1u) && r[0x2540/4]==1 && !r[0x2544/4] && r[0x2548/4]==60 &&
        !r[0x254c/4] && (r[0x2580/4]==0 || r[0x2580/4]==0x12000) &&
        r[0x22d0/4]==0xc1e && r[0x22bc/4]==3;
}

static void input_statistics_invalidate(Z72InputConfig *s)
{
    Z62InputReadout *r=&s->input_readout;
    g_clear_pointer(&r->completed_pixels,g_free);r->stats_valid=false;
    memset(&r->stats_latest,0,sizeof(r->stats_latest));
}

static void input_statistics_capture(Z72InputConfig *s)
{
    Z62InputReadout *r=&s->input_readout;
    if (!input_statistics_phase(s)) return;
    /* The admitted mailbox can be replaced later; keep the last completed
     * image separate from both the next lease and the current finite batch. */
    uint8_t *pixels=g_memdup2(r->lease.pixels,r->lease.meta.bytes);
    g_free(r->completed_pixels);r->completed_pixels=pixels;
    r->stats_latest=r->lease.meta;r->stats_serial=r->completed;r->stats_valid=true;
    if (!s->finite_active && !s->finite_done && s->finite_reason==1)
        s->finite_rearm=true; /* Actual source arrival, not a success event. */
}

static bool input_statistics_pixels(Z72InputConfig *s)
{
    Z62InputReadout *r=&s->input_readout;
    if (!r->stats_valid || !r->completed_pixels || !input_statistics_phase(s)) return false;
    memset(s->finite_pixels,0,sizeof(s->finite_pixels));
    for (unsigned y=0;y<12;y++) for (unsigned x=0;x<30;x++) {
        uint64_t sum=0;unsigned count=0;
        for (unsigned sy=y*136/12;sy<(y+1)*136/12;sy++)
            for (unsigned sx=x*2020/30;sx<(x+1)*2020/30;sx++) {
                const uint8_t *p=r->completed_pixels+(size_t)sy*r->stats_latest.stride+2*sx;
                sum+=lduw_le_p(p)>>4;count++;
            }
        stw_le_p(s->finite_pixels+y*64+x*2,(sum+count/2)/count);
    }
    return true;
}

static void input_statistics_select(Z72InputConfig *s)
{
    Z62InputReadout *r=&s->input_readout;
    r->stats_batch=r->stats_latest;r->stats_batch_serial=r->stats_serial;r->stats_batches++;
}

static void input_statistics_reset(Z72InputConfig *s)
{
    Z62InputReadout *r=&s->input_readout;input_statistics_invalidate(s);
    memset(&r->stats_batch,0,sizeof(r->stats_batch));r->statistics_job=false;
    r->stats_serial=r->stats_batch_serial=r->stats_batches=0;
}

static char *input_statistics_status(Object *obj,Error **errp)
{
    Z72InputConfig *s=Z72_INPUT_CONFIG(obj);Z62InputReadout *r=&s->input_readout;
    return g_strdup_printf("{\"enabled\":%s,\"phase\":%s,\"valid\":%s,"
        "\"latest_publication\":%" PRIu64 ",\"completed_source_serial\":%" PRIu64 ","
        "\"batches\":%" PRIu64 ",\"batch_source_serial\":%" PRIu64 ","
        "\"batch_epoch\":%" PRIu64 ",\"batch_publication\":%" PRIu64 ","
        "\"batch_frame\":%" PRIu64 ",\"batch_time_ns\":%" PRIu64 ","
        "\"finite_frames\":%" PRIu64 ",\"new_RAW_acquisitions\":false,"
        "\"math\":\"C-linear16-shift4-box-means-retained-per-batch\"}",
        r->stats_enabled?"true":"false",input_statistics_phase(s)?"true":"false",r->stats_valid?"true":"false",
        r->stats_latest.publication,r->stats_serial,r->stats_batches,r->stats_batch_serial,
        r->stats_batch.epoch,r->stats_batch.publication,r->stats_batch.frame,r->stats_batch.time_ns,s->finite_frames);
}
