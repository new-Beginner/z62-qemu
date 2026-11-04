/* SPDX-License-Identifier: GPL-2.0-or-later
 * BQL-owned four-frame linear source bridge. No guessed guest-ready/event6,
 * original RAW memory edits or legacy RAW counter increments.
 */
static bool preview_ready(NikonZ72BootConfig *s);
static void preview_schedule(NikonZ72BootConfig *s);
static void preview_cancel(NikonZ72BootConfig *s);

static void cw_preview_discard(NikonZ72BootConfig *s)
{
    if (s->cw_preview.owns) {preview_cancel(s);s->preview_source_valid=false;}
    s->cw_preview.owns=false;
    for (unsigned i=0;i<4;i++) g_clear_pointer(&s->cw_preview.linear[i],g_free);
}

static void cw_preview_event(void *opaque,int line,int level)
{
    NikonZ72BootConfig *s=opaque;Z62CWPreviewCache *c=&s->cw_preview;Z62CWCohortView view;
    if (!level) return;
    if (line==1) {cw_preview_discard(s);return;}
    if (!z62_capturework_cohort_view(s->paired_input,&view)) {c->rejected++;return;}
    if (view.sequence<=c->last_seen) {c->stale++;return;}
    c->last_seen=view.sequence;
    /* Existing lineage/paired/video contracts do not describe this new source.
     * Reject those contexts instead of mislabelling a CW frame as old RAW. */
    if (!preview_supported(s) || s->z62_paired_ingress || s->z62_output_lineage) {c->rejected++;return;}
    if (s->preview_source_valid && s->preview_source_seq>s->preview_last_seq) {c->blocked++;return;}
    uint64_t previous=MAX(s->preview_source_seq,s->preview_last_seq);
    if (previous==UINT64_MAX) {c->rejected++;return;}
    cw_preview_discard(s);
    for (unsigned i=0;i<4;i++) {
        c->linear[i]=g_memdup2(view.linear[i],Z62_CW_COHORT_BYTES);
        c->address[i]=view.address[i];c->meta[i]=view.meta[i];
        g_strlcpy(c->sha256[i],view.sha256[i],sizeof(c->sha256[i]));
        s->preview_source[i]=view.address[i];
    }
    c->generation=view.generation;c->sequence=view.sequence;c->bank=view.bank;c->owns=true;c->accepted++;
    s->preview_source_seq=previous+1;s->preview_source_valid=true;preview_schedule(s);
}

static bool cw_preview_read(NikonZ72BootConfig *s,uint32_t address,uint8_t *data,size_t bytes)
{
    if (s->cw_preview.owns) {
        if (bytes!=Z62_CW_COHORT_BYTES) return false;
        for (unsigned i=0;i<4;i++) if (address==s->cw_preview.address[i] && s->cw_preview.linear[i]) {
            memcpy(data,s->cw_preview.linear[i],bytes);return true;
        }
        return false;
    }
    return address_space_read(&s->preview_memory,address,MEMTXATTRS_UNSPECIFIED,data,bytes)==MEMTX_OK;
}

static void cw_preview_reset(NikonZ72BootConfig *s)
{ cw_preview_discard(s);memset(&s->cw_preview,0,sizeof(s->cw_preview)); }

static char *cw_preview_status(Object *obj,Error **errp)
{
    NikonZ72BootConfig *s=NIKON_Z72_BOOT_CONFIG(obj);Z62CWPreviewCache *c=&s->cw_preview;
    GString *out=g_string_new(NULL);
    g_string_append_printf(out,"{\"source_enabled\":%s,\"owns_source\":%s,\"source_valid\":%s,\"consumer_ready\":%s,"
        "\"accepted\":%" PRIu64 ",\"blocked\":%" PRIu64 ",\"rejected\":%" PRIu64 ",\"stale\":%" PRIu64 ","
        "\"cohort\":%" PRIu64 ",\"generation\":%" PRIu64 ",\"bank\":%u,"
        "\"source_seq\":%" PRIu64 ",\"consumed_seq\":%" PRIu64 ","
        "\"consumer_controls\":[%u,%u,%u,%u],\"frames\":[",
        z62_capturework_preview_enabled(s->paired_input)?"true":"false",c->owns?"true":"false",
        s->preview_source_valid?"true":"false",preview_ready(s)?"true":"false",c->accepted,c->blocked,c->rejected,c->stale,
        c->sequence,c->generation,c->bank,s->preview_source_seq,s->preview_last_seq,
        ldl_le_p(s->transfer_table+4),s->preview_raw[8/4],s->preview_core[0x2100/4],s->preview_core[0x2608/4]);
    for (unsigned i=0;i<4;i++) g_string_append_printf(out,
        "%s{\"address\":%u,\"epoch\":%" PRIu64 ",\"publication\":%" PRIu64 ","
        "\"frame\":%" PRIu64 ",\"time_ns\":%" PRIu64 ",\"linear_sha256\":\"%s\"}",i?",":"",
        c->address[i],c->meta[i].epoch,c->meta[i].publication,c->meta[i].frame,c->meta[i].time_ns,c->sha256[i]);
    g_string_append(out,"]}");return g_string_free(out,false);
}
