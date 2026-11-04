/* SPDX-License-Identifier: GPL-2.0-or-later
 * Four distinct actually completed CW slots, same epoch/configuration/bank.
 * No guest events or RAW counters. Never duplicate one frame into four slots.
 */
static void cw_cohort_cancel(Z72InputConfig *s)
{
    Z62CWCohort *c=&s->cw_cohort;
    bool had_data=c->mask || c->valid;
    c->mask=0;c->valid=false;
    for (unsigned i=0;i<4;i++) g_clear_pointer(&c->linear[i],g_free);
    memset(c->address,0,sizeof(c->address));memset(c->meta,0,sizeof(c->meta));
    memset(c->transfer,0,sizeof(c->transfer));memset(c->sha256,0,sizeof(c->sha256));
    if (c->enabled && had_data) {
        c->invalidated++;
        if (!s->cw.stopping) qemu_irq_pulse(c->event[1]);
    }
}

static bool cw_cohort_collect(Z72InputConfig *s,Z62CWTask *task)
{
    Z62CWCohort *c=&s->cw_cohort;
    if (!c->enabled) return false;
    if (!task->statistics_linear || task->pixels.output_width!=1514 || task->pixels.output_height!=1006 ||
        task->pixels.output_stride!=2272 || task->pixels.bits!=12 || task->profile.buffers[7]!=3 || task->slot>3) {
        c->rejected++;cw_cohort_cancel(s);return false;
    }
    if ((c->mask || c->valid) && (c->generation!=task->generation || c->bank!=task->bank || c->epoch!=task->lease.meta.epoch))
        cw_cohort_cancel(s);
    c->valid=false;c->generation=task->generation;c->bank=task->bank;c->epoch=task->lease.meta.epoch;
    unsigned i=task->slot;uint8_t *data=g_memdup2(task->statistics_linear,Z62_CW_COHORT_BYTES);
    g_free(c->linear[i]);c->linear[i]=data;c->address[i]=task->destination;
    c->meta[i]=task->lease.meta;c->transfer[i]=task->transfer;
    gchar *sha=g_compute_checksum_for_data(G_CHECKSUM_SHA256,data,Z62_CW_COHORT_BYTES);
    g_strlcpy(c->sha256[i],sha,sizeof(c->sha256[i]));g_free(sha);
    c->mask|=1u<<i;c->collected++;
    if (c->mask!=15) return false;
    for (unsigned a=0;a<4;a++) for (unsigned b=0;b<a;b++) {
        if (c->meta[a].publication==c->meta[b].publication || c->address[a]==c->address[b]) {
            c->rejected++;cw_cohort_cancel(s);return false;
        }
    }
    if (c->sequence==UINT64_MAX) {c->rejected++;cw_cohort_cancel(s);return false;}
    c->mask=0;c->valid=true;c->sequence++;return true;
}

bool z62_capturework_preview_enabled(DeviceState *dev)
{ return dev && Z72_INPUT_CONFIG(dev)->cw_cohort.enabled; }

bool z62_capturework_cohort_view(DeviceState *dev,Z62CWCohortView *view)
{
    if (!dev || !view) return false;
    Z62CWCohort *c=&Z72_INPUT_CONFIG(dev)->cw_cohort;
    if (!c->enabled || !c->valid || c->mask) return false;
    memset(view,0,sizeof(*view));view->bank=c->bank;view->generation=c->generation;view->sequence=c->sequence;
    for (unsigned i=0;i<4;i++) {
        view->linear[i]=c->linear[i];view->address[i]=c->address[i];view->meta[i]=c->meta[i];
        view->transfer[i]=c->transfer[i];g_strlcpy(view->sha256[i],c->sha256[i],sizeof(view->sha256[i]));
    }
    return true;
}

static char *cw_cohort_status(Object *obj,Error **errp)
{
    Z62CWCohort *c=&Z72_INPUT_CONFIG(obj)->cw_cohort;
    GString *out=g_string_new(NULL);
    g_string_append_printf(out,"{\"enabled\":%s,\"valid\":%s,\"collecting_mask\":%u,"
        "\"cohorts\":%" PRIu64 ",\"collected_frames\":%" PRIu64 ",\"invalidated\":%" PRIu64 ","
        "\"rejected\":%" PRIu64 ",\"generation\":%" PRIu64 ",\"bank\":%u,\"frames\":[",
        c->enabled?"true":"false",c->valid?"true":"false",c->mask,c->sequence,c->collected,c->invalidated,c->rejected,c->generation,c->bank);
    for (unsigned i=0;i<4;i++) g_string_append_printf(out,
        "%s{\"address\":%u,\"epoch\":%" PRIu64 ",\"publication\":%" PRIu64 ","
        "\"frame\":%" PRIu64 ",\"time_ns\":%" PRIu64 ",\"linear_sha256\":\"%s\"}",i?",":"",
        c->address[i],c->meta[i].epoch,c->meta[i].publication,c->meta[i].frame,c->meta[i].time_ns,c->sha256[i]);
    g_string_append(out,"]}");return g_string_free(out,false);
}
