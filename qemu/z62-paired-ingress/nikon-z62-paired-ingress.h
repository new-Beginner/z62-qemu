/* SPDX-License-Identifier: GPL-2.0-or-later
 * Explicit level-C input for the existing level-C ISP. This is not a recovered
 * sensor protocol. It does not rearm RAW, run statistics, or emit completion.
 * Only the existing ISP may complete, after it computes and writes outputs.
 */
#define PAIRED_INGRESS_PERIOD_NS 33333333
static void preview_schedule(NikonZ72BootConfig *s);

enum { PAIRED_RESET, PAIRED_IDLE, PAIRED_LEGACY_ACTIVE, PAIRED_BACKPRESSURE,
       PAIRED_PROFILE, PAIRED_ADDRESS, PAIRED_RAM, PAIRED_ALIAS,
       PAIRED_SCENE, PAIRED_IO, PAIRED_SUCCESS, PAIRED_SEQUENCE };

static void paired_ingress_stop(NikonZ72BootConfig *s)
{
    s->paired_ingress_active = false;
    timer_del(s->paired_ingress_timer);
    if (s->paired_ingress_owns_source) {
        s->preview_source_valid = false;
        video_cancel(s);
        s->paired_ingress_owns_source = false;
    }
}

static bool paired_ingress_profile(NikonZ72BootConfig *s)
{
    bool photo = s->preview_raw[0x48/4] == 0x05ea03ee &&
        s->preview_raw[0x30c/4] == 2272 && s->preview_core[0x2600/4] == 0x305 &&
        s->preview_core[0x2604/4] == 1002 && s->preview_core[0x2608/4] == 1;
    bool movie = s->z62_video_isp && z62_video_paired_profile(s->preview_raw) &&
        s->preview_core[0x2600/4] == 0x300 && s->preview_core[0x2604/4] == 846 &&
        s->preview_core[0x2608/4] == 3;
    return (photo || movie) && s->preview_raw[0x300/4] == 0 &&
        s->preview_raw[8/4] == 1 && s->preview_raw[0x10/4] == 1 &&
        s->preview_core[0x2100/4] == 0x121 && (ldl_le_p(s->transfer_table+4)&1);
}

static unsigned paired_ingress_spans(NikonZ72BootConfig *s, uint32_t source[4])
{
    Z62VideoSpan spans[44]; unsigned used = 0, why;
    bool movie = s->preview_core[0x2600/4] == 0x300;
    /* Preflight backing RAM, not just virtual ranges. Input aliases with
     * each other or with any configured output are rejected before DMA. */
    for (unsigned f = 0; f < 4; f++) {
        uint64_t address = s->preview_raw[0x310/4+f];
        if ((address&3) || address < 0x82c00000 ||
            address+Z62_PAIRED_SCENE_BYTES > 0x8aebc400) return PAIRED_ADDRESS;
        if (!preview_ram(s,address,Z62_PAIRED_SCENE_BYTES,true)) return PAIRED_RAM;
        why = video_span(s,spans,&used,address,Z62_PAIRED_SCENE_BYTES,9,f,false);
        if (why) return why == 4 ? PAIRED_ALIAS : PAIRED_RAM;
        source[f] = address;
    }
    for (unsigned f = 0; f < 4; f++) {
        for (unsigned c = 0; c < 3; c++) {
            const uint32_t *r = &s->preview_core[(0x400+(c+3)*64)/4];
            uint32_t w=r[8]&0x7fff, h=r[8]>>16, stride=r[4], uv=r[10];
            if (r[0]!=0x09000201 || (r[8]&0x8000) || !w || !h || (w&1) || (h&1) ||
                w>1920 || h>1080 || stride<w || stride>2048 || r[5]!=stride ||
                (uint64_t)stride*h>uv) return PAIRED_PROFILE;
            uint64_t address=s->preview_core[0x2200/4+f*16+c+3];
            uint64_t bytes=(uint64_t)stride*h;
            if ((address&15) || !preview_pool(address,bytes) ||
                !preview_pool(address+uv,bytes/2)) return PAIRED_ADDRESS;
            why=video_span(s,spans,&used,address,bytes,c,f,true);
            if (why) return why == 4 ? PAIRED_ALIAS : PAIRED_RAM;
            why=video_span(s,spans,&used,address+uv,bytes/2,c,f,true);
            if (why) return why == 4 ? PAIRED_ALIAS : PAIRED_RAM;
        }
        if (movie) {
            for (unsigned p=0;p<2;p++) {
                uint64_t main=s->preview_raw[(p ? 0x498 : 0x488)/4+f];
                uint64_t work=s->preview_raw[(p ? 0x440 : 0x430)/4+f];
                uint64_t bytes=p ? Z62_VIDEO_MAIN_Y_BYTES/2 : Z62_VIDEO_MAIN_Y_BYTES;
                if ((main&15) || (work&15) || !preview_pool(main,bytes) ||
                    !preview_pool(work,Z62_VIDEO_WORK_BYTES)) return PAIRED_ADDRESS;
                why=video_span(s,spans,&used,main,bytes,3,f,true);
                if (why) return why == 4 ? PAIRED_ALIAS : PAIRED_RAM;
                why=video_span(s,spans,&used,work,Z62_VIDEO_WORK_BYTES,4+p,f,true);
                if (why) return why == 4 ? PAIRED_ALIAS : PAIRED_RAM;
            }
        }
    }
    return PAIRED_SUCCESS;
}

static void paired_ingress_tick(void *opaque)
{
    NikonZ72BootConfig *s=opaque;
    if (!s->z62_paired_ingress || !s->paired_ingress_active || !preview_supported(s)) return;
    timer_mod(s->paired_ingress_timer,qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL)+PAIRED_INGRESS_PERIOD_NS);
    s->paired_ingress_attempts++;
    if (raw_stream_running(s)) { s->paired_ingress_reason=PAIRED_LEGACY_ACTIVE; return; }
    if (!paired_ingress_profile(s) || s->preview_stopping) {
        s->paired_ingress_reason=PAIRED_PROFILE; return;
    }
    if (preview_results_pending(s) || (ldl_le_p(s->transfer_table+0x20)&8) ||
        (s->preview_raw[0x24/4]&0x1002) ||
        (s->preview_source_valid && s->preview_source_seq>s->preview_last_seq)) {
        s->paired_ingress_reason=PAIRED_BACKPRESSURE; s->paired_ingress_blocked++; return;
    }
    uint64_t sequence=MAX(s->preview_source_seq,s->preview_last_seq), tags[4];
    if (sequence==UINT64_MAX) { s->paired_ingress_reason=PAIRED_SEQUENCE; return; }
    uint32_t source[4]; unsigned reason=paired_ingress_spans(s,source);
    if (reason!=PAIRED_SUCCESS) { s->paired_ingress_reason=reason; s->paired_ingress_rejected++; return; }
    g_autofree uint8_t *pixels=g_malloc(Z62_PAIRED_SCENE_BYTES);
    if (!s->paired_input || !z62_paired_scene_copy(s->paired_input,pixels,tags)) {
        s->paired_ingress_reason=PAIRED_SCENE; return;
    }
    /* BQL keeps the source, mappings and configuration stable across the
     * snapshot and four writes. A failure never publishes a generation. */
    for (unsigned f=0;f<4;f++) {
        if (address_space_write(&s->preview_memory,source[f],MEMTXATTRS_UNSPECIFIED,
                                pixels,Z62_PAIRED_SCENE_BYTES)!=MEMTX_OK) {
            s->paired_ingress_reason=PAIRED_IO; s->paired_ingress_rejected++; return;
        }
    }
    if (!z62_paired_scene_used(s->paired_input,tags)) {
        s->paired_ingress_reason=PAIRED_SCENE; s->paired_ingress_rejected++; return;
    }
    memcpy(s->preview_source,source,sizeof(source));
    memcpy(s->paired_ingress_tags,tags,sizeof(tags));
    s->paired_ingress_dma_ns=qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL);
    s->paired_ingress_frames++; s->paired_ingress_bytes+=4ull*Z62_PAIRED_SCENE_BYTES;
    s->paired_ingress_reason=PAIRED_SUCCESS; s->paired_ingress_owns_source=true;
    s->preview_source_seq=sequence+1; s->preview_source_valid=true;
    video_source_notify(s);
    preview_schedule(s);
    /* Deliberately no IRQ, statistics result, raw_stream_started or guest
     * ready/queue update here. Downstream computation owns completion. */
}

static void paired_ingress_control(NikonZ72BootConfig *s, hwaddr address, uint32_t value)
{
    if (!s->z62_paired_ingress || !s->master_role || !preview_supported(s)) return;
    if ((address==0x20102608 && !(value&1)) || (address==0x20100004 && !(value&1)) ||
        ((address==0x20380008 || address==0x20380010) && !(value&1)) ||
        (address==0x203800f0 && value==0xfc400)) {
        paired_ingress_stop(s);
    } else if (address==0x20380008 && value==1 &&
               (s->preview_raw[0x48/4]==0x05ea03ee || s->preview_raw[0x48/4]==0x05ec0356)) {
        s->paired_ingress_active=true;
        timer_mod(s->paired_ingress_timer,qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL)+PAIRED_INGRESS_PERIOD_NS);
    }
}

static void paired_ingress_reset(NikonZ72BootConfig *s)
{
    paired_ingress_stop(s);
    s->paired_ingress_attempts=s->paired_ingress_frames=s->paired_ingress_bytes=0;
    s->paired_ingress_rejected=s->paired_ingress_blocked=s->paired_ingress_dma_ns=0;
    memset(s->paired_ingress_tags,0,sizeof(s->paired_ingress_tags));
    s->paired_ingress_reason=PAIRED_RESET;
}

static char *paired_ingress_reason_get(Object *obj, Error **errp)
{
    NikonZ72BootConfig *s=NIKON_Z72_BOOT_CONFIG(obj);
    static const char *const names[]={"reset","idle","legacy-raw-active","backpressure",
        "profile","address","ram","alias","scene-missing","dma-error","success","sequence-overflow"};
    return g_strdup(s->paired_ingress_reason<G_N_ELEMENTS(names) ? names[s->paired_ingress_reason] : "invalid");
}

static bool paired_ingress_active_get(Object *obj, Error **errp)
{
    return NIKON_Z72_BOOT_CONFIG(obj)->paired_ingress_active;
}

static void paired_ingress_init(Object *obj)
{
    NikonZ72BootConfig *s=NIKON_Z72_BOOT_CONFIG(obj);
    s->paired_ingress_timer=timer_new_ns(QEMU_CLOCK_VIRTUAL,paired_ingress_tick,s);
    object_property_add_bool(obj,"paired-ingress-active",paired_ingress_active_get,NULL);
    object_property_add_uint64_ptr(obj,"paired-ingress-attempts",&s->paired_ingress_attempts,OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(obj,"paired-ingress-frames",&s->paired_ingress_frames,OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(obj,"paired-ingress-bytes",&s->paired_ingress_bytes,OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(obj,"paired-ingress-rejected",&s->paired_ingress_rejected,OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(obj,"paired-ingress-blocked",&s->paired_ingress_blocked,OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(obj,"paired-ingress-publish-id",&s->paired_ingress_tags[1],OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(obj,"paired-ingress-dma-time-ns",&s->paired_ingress_dma_ns,OBJ_PROP_FLAG_READ);
    object_property_add_str(obj,"paired-ingress-reason",paired_ingress_reason_get,NULL);
}
