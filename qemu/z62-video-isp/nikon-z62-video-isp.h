/* SPDX-License-Identifier: GPL-2.0-or-later
 * r59 explicit software video transaction. Include after preview RAM helpers.
 * It never completes bank0 or manufactures statistics / source generations.
 */
#include "nikon-z62-video-profile.h"

#define Z62_VIDEO_COHORT_BYTES (4u*Z62_VIDEO_INPUT_BYTES)

static bool video_origin_valid(NikonZ72BootConfig *s)
{
    return s->video_origin_x>=-4096 && s->video_origin_x<=4096 &&
        s->video_origin_y>=-4096 && s->video_origin_y<=4096 &&
        !(s->video_origin_x%2) && !(s->video_origin_y%2);
}

static bool video_configuration(NikonZ72BootConfig *s,Error **errp)
{
    if(s->z62_video_isp && (!s->z62_preview || !s->z62_preview_results || !video_origin_valid(s))) {
        error_setg(errp,"z62-video-isp needs preview/results and explicit even video-origin-x/y in [-4096,4096]");
        return false;
    }
    return true;
}

static void video_drop_source(NikonZ72BootConfig *s)
{
    s->video_source_valid=false;s->video_source_bytes=0;s->video_source_seq=0;
    memset(s->video_source_address,0,sizeof(s->video_source_address));
}

static void video_cancel(NikonZ72BootConfig *s)
{
    if(s->video_source_valid) s->video_source_cancelled++;
    video_drop_source(s);
    z62_video_pixels_free(s->video_pixels);s->video_pixels=NULL;
}

static void video_reset(NikonZ72BootConfig *s)
{
    video_cancel(s);
    memset(s->video_source_data,0,sizeof(s->video_source_data));
    s->video_captures=s->video_coalesced=s->video_source_rejected=s->video_source_cancelled=0;
    s->video_batches=s->video_main_bytes=s->video_work_bytes=s->video_rejected=s->video_blocked=0;
    s->video_reason=0;
}

static int video_pre_load(void *opaque)
{
    NikonZ72BootConfig *s=opaque;
    z62_video_pixels_free(s->video_pixels);s->video_pixels=NULL;
    return 0;
}

static int video_post_load(NikonZ72BootConfig *s)
{
    if(s->video_reason>8 || (s->z62_video_isp && !video_origin_valid(s)) ||
       s->video_source_bytes!=(s->video_source_valid ? Z62_VIDEO_COHORT_BYTES:0)) return -EINVAL;
    if(s->video_batches>s->preview_batches || s->video_batches>UINT64_MAX/(8ull*Z62_VIDEO_WORK_BYTES) ||
       s->video_batches>UINT64_MAX/(4ull*Z62_VIDEO_MAIN_BYTES) ||
       s->video_main_bytes!=s->video_batches*4ull*Z62_VIDEO_MAIN_BYTES ||
       s->video_work_bytes!=s->video_batches*8ull*Z62_VIDEO_WORK_BYTES) return -EINVAL;
    if(s->video_source_valid) {
        if(!s->z62_video_isp || !s->master_role || !s->video_source_seq ||
           s->video_source_seq!=s->preview_source_seq || s->video_source_seq<=s->preview_last_seq) return -EINVAL;
        for(unsigned i=0;i<4;i++) {
            uint64_t address=s->video_source_address[i];
            if(address<0x82c00000 || address+Z62_VIDEO_INPUT_BYTES>0x8aebc400 ||
               memcmp(s->video_source_data,s->video_source_data+i*Z62_VIDEO_INPUT_BYTES,Z62_VIDEO_INPUT_BYTES)) return -EINVAL;
        }
    } else {
        if(s->video_source_seq) return -EINVAL;
        for(unsigned i=0;i<4;i++) if(s->video_source_address[i]) return -EINVAL;
    }
    return 0;
}

static void video_source_notify(NikonZ72BootConfig *s)
{
    if(!s->z62_video_isp || !preview_supported(s) || s->preview_raw[0x48/4]!=0x05ec0356) return;
    if(s->video_source_valid) s->video_coalesced++;
    video_drop_source(s);
    for(unsigned i=0;i<4;i++) {
        uint64_t address=s->preview_source[i];
        if(address<0x82c00000 || address+Z62_VIDEO_INPUT_BYTES>0x8aebc400 ||
           !preview_ram(s,address,Z62_VIDEO_INPUT_BYTES,false) ||
           address_space_read(&s->preview_memory,address,MEMTXATTRS_UNSPECIFIED,
               s->video_source_data+i*Z62_VIDEO_INPUT_BYTES,Z62_VIDEO_INPUT_BYTES)!=MEMTX_OK) goto rejected;
        s->video_source_address[i]=address;
    }
    /* The qualified four-phase output rings alias. Until per-phase ownership
     * is modelled, admit only an actual identical four-slot RAW cohort. */
    for(unsigned i=1;i<4;i++)
        if(memcmp(s->video_source_data,s->video_source_data+i*Z62_VIDEO_INPUT_BYTES,Z62_VIDEO_INPUT_BYTES)) goto rejected;
    s->video_source_seq=s->preview_source_seq;s->video_source_bytes=Z62_VIDEO_COHORT_BYTES;
    s->video_source_valid=true;s->video_captures++;
    return;
rejected:
    video_drop_source(s);s->video_source_rejected++;s->video_reason=2;
}

typedef struct Z62VideoSpan {
    MemoryRegion *ram; uint64_t offset,bytes; unsigned channel,phase; bool output;
} Z62VideoSpan;

static unsigned video_span(NikonZ72BootConfig *s,Z62VideoSpan *spans,unsigned *count,
                           uint64_t address,uint64_t bytes,unsigned channel,unsigned phase,bool output)
{
    if(*count>=44 || !preview_ram(s,address,bytes,output)) return 3;
    hwaddr offset,available=bytes;
    MemoryRegion *ram=address_space_translate(&s->preview_memory,address,&offset,&available,output,MEMTXATTRS_UNSPECIFIED);
    if(!ram || available<bytes || offset>UINT64_MAX-bytes) return 3;
    for(unsigned i=0;i<*count;i++) {
        Z62VideoSpan *old=&spans[i];
        if(old->ram==ram && offset<old->offset+old->bytes && old->offset<offset+bytes &&
           !(output && old->output && channel==old->channel && phase!=old->phase &&
             offset==old->offset && bytes==old->bytes)) return 4;
    }
    spans[(*count)++]=(Z62VideoSpan){ram,offset,bytes,channel,phase,output};
    return 0;
}

static void video_tick(NikonZ72BootConfig *s)
{
    if(preview_results_pending(s) || (ldl_le_p(s->transfer_table+0x20)&8) || (s->preview_raw[0x24/4]&0x1002)) {
        s->video_blocked++;s->preview_blocked++;s->video_reason=8;return;
    }
    /* RAM left by an old mode is never a video source. */
    if(!s->video_source_valid || s->video_source_seq!=s->preview_source_seq ||
       s->video_source_seq<=s->preview_last_seq) { s->video_reason=2;return; }
    uint64_t sequence=s->video_source_seq;
    uint32_t widths[3],heights[3],strides[3],uv[3],dest[4][3],main[4][2],work[4][2];
    Z62VideoSpan spans[44];unsigned used=0,reason=1;
    if(!video_origin_valid(s) || !z62_video_paired_profile(s->preview_raw) ||
       s->preview_core[0x2100/4]!=0x121 || s->preview_core[0x2110/4]!=0x200087e0 ||
       s->preview_core[0x2114/4]!=0x88000 || s->preview_core[0x2600/4]!=0x300 ||
       s->preview_core[0x2604/4]!=846 || s->preview_core[0x2608/4]!=3) goto rejected;
    for(unsigned c=0;c<3;c++) {
        const uint32_t *p=&s->preview_core[(0x400+(c+3)*64)/4];
        if(!z62_video_port_profile(c+3,p)) goto rejected;
        widths[c]=p[8]&0x7fff;heights[c]=p[8]>>16;strides[c]=p[4];uv[c]=p[10];
    }
    if(!z62_video_port_profile(8,&s->preview_core[0x600/4]) ||
       !preview_results_prepare(s,widths,heights)) goto rejected;
    for(unsigned f=0;f<4;f++) {
        uint32_t source=s->preview_raw[0x310/4+f];bool supplied=false;
        for(unsigned i=0;i<4;i++) supplied|=source==s->video_source_address[i];
        reason=2;if(!supplied) goto rejected;
        reason=video_span(s,spans,&used,s->video_source_address[f],Z62_VIDEO_INPUT_BYTES,9,f,false);
        if(reason) goto rejected;
        main[f][0]=s->preview_raw[0x488/4+f];main[f][1]=s->preview_raw[0x498/4+f];
        work[f][0]=s->preview_raw[0x430/4+f];work[f][1]=s->preview_raw[0x440/4+f];
        reason=1;
        if(s->preview_core[0x2200/4+f*16+8]!=main[f][0] ||
           s->preview_raw[0x4a8/4+f]!=main[f][0] || s->preview_raw[0x4b8/4+f]!=main[f][1] ||
           s->preview_raw[0x450/4+f]!=work[f][0] || s->preview_raw[0x460/4+f]!=work[f][1] ||
           (uint64_t)main[f][0]+Z62_VIDEO_MAIN_Y_BYTES!=main[f][1] ||
           (uint64_t)work[f][0]+Z62_VIDEO_WORK_BYTES!=work[f][1]) goto rejected;
        for(unsigned plane=0;plane<2;plane++) {
            uint64_t mbytes=plane ? Z62_VIDEO_MAIN_Y_BYTES/2:Z62_VIDEO_MAIN_Y_BYTES;
            reason=3;
            if((main[f][plane]&15) || (work[f][plane]&15) || !preview_pool(main[f][plane],mbytes) ||
               !preview_pool(work[f][plane],Z62_VIDEO_WORK_BYTES)) goto rejected;
            reason=video_span(s,spans,&used,main[f][plane],mbytes,3,f,true);if(reason) goto rejected;
            reason=video_span(s,spans,&used,work[f][plane],Z62_VIDEO_WORK_BYTES,4+plane,f,true);if(reason) goto rejected;
        }
        for(unsigned c=0;c<3;c++) {
            dest[f][c]=s->preview_core[0x2200/4+f*16+c+3];
            uint64_t address=dest[f][c],bytes=(uint64_t)strides[c]*heights[c];
            reason=3;
            if((address&15) || !preview_pool(address,bytes) || !preview_pool(address+uv[c],bytes/2)) goto rejected;
            reason=video_span(s,spans,&used,address,bytes,c,f,true);if(reason) goto rejected;
            reason=video_span(s,spans,&used,address+uv[c],bytes/2,c,f,true);if(reason) goto rejected;
        }
    }
    reason=5;
    if(!s->video_pixels) s->video_pixels=z62_video_pixels_new();
    if(!s->video_pixels || !z62_video_pixels_input(s->video_pixels,s->video_source_data,Z62_VIDEO_INPUT_BYTES,
                                                   s->video_origin_x,s->video_origin_y)) goto rejected;
    const uint8_t *pixels[3];
    for(unsigned c=0;c<3;c++) {
        pixels[c]=z62_video_pixels_render(s->video_pixels,c,widths[c],heights[c],strides[c]);
        if(!pixels[c]) goto rejected;
    }
    /* All backing, alias, profile and private arithmetic checks precede DMA.
     * No original software queues, callback packets or ready words are written. */
    reason=6;
    for(unsigned f=0;f<4;f++) {
        for(unsigned plane=0;plane<2;plane++) {
            size_t size=plane ? Z62_VIDEO_MAIN_Y_BYTES/2:Z62_VIDEO_MAIN_Y_BYTES;
            const uint8_t *m=s->video_pixels->main+(plane ? Z62_VIDEO_MAIN_Y_BYTES:0);
            if(address_space_write(&s->preview_memory,main[f][plane],MEMTXATTRS_UNSPECIFIED,m,size)!=MEMTX_OK ||
               address_space_write(&s->preview_memory,work[f][plane],MEMTXATTRS_UNSPECIFIED,
                 s->video_pixels->work+plane*Z62_VIDEO_WORK_BYTES,Z62_VIDEO_WORK_BYTES)!=MEMTX_OK) goto rejected;
        }
        for(unsigned c=0;c<3;c++) {
            size_t ybytes=(size_t)strides[c]*heights[c];
            if(address_space_write(&s->preview_memory,dest[f][c],MEMTXATTRS_UNSPECIFIED,pixels[c],ybytes)!=MEMTX_OK ||
               address_space_write(&s->preview_memory,(uint64_t)dest[f][c]+uv[c],MEMTXATTRS_UNSPECIFIED,
                                   pixels[c]+ybytes,ybytes/2)!=MEMTX_OK) goto rejected;
        }
    }
    s->preview_last_seq=sequence;s->preview_batches++;s->preview_outputs+=12;
    for(unsigned c=0;c<3;c++) s->preview_bytes+=4ull*strides[c]*heights[c]*3/2;
    s->preview_reason=8;s->video_reason=7;s->video_batches++;
    s->video_main_bytes+=4ull*Z62_VIDEO_MAIN_BYTES;s->video_work_bytes+=8ull*Z62_VIDEO_WORK_BYTES;
    video_drop_source(s);
    stl_le_p(s->transfer_table+0x20,ldl_le_p(s->transfer_table+0x20)|8);
    s->preview_raw[0x24/4]|=0x1002;
    preview_results_finish(s);transfer_update_irq(s);preview_irq99(s);
    return;
rejected:
    s->preview_last_seq=sequence;s->preview_reason=reason==1 ? 10:reason==2 ? 1:reason==3 ? 4:reason==4 ? 5:6;
    s->video_reason=reason;s->video_rejected++;s->preview_rejected++;video_drop_source(s);
}

static char *video_reason_get(Object *obj,Error **errp)
{
    NikonZ72BootConfig *s=NIKON_Z72_BOOT_CONFIG(obj);
    static const char *const names[]={"reset","configuration","source","destination","alias",
        "pixels-or-allocation","dma-error","success","backpressure"};
    return g_strdup(s->video_reason<G_N_ELEMENTS(names) ? names[s->video_reason]:"invalid");
}

static void video_qom_init(Object *obj)
{
    NikonZ72BootConfig *s=NIKON_Z72_BOOT_CONFIG(obj);
    object_property_add_uint64_ptr(obj,"video-batches",&s->video_batches,OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(obj,"video-main-bytes",&s->video_main_bytes,OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(obj,"video-work-bytes",&s->video_work_bytes,OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(obj,"video-rejected",&s->video_rejected,OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(obj,"video-blocked",&s->video_blocked,OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(obj,"video-source-captures",&s->video_captures,OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(obj,"video-source-coalesced",&s->video_coalesced,OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(obj,"video-source-rejected",&s->video_source_rejected,OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(obj,"video-source-cancelled",&s->video_source_cancelled,OBJ_PROP_FLAG_READ);
    object_property_add_uint32_ptr(obj,"video-source-bytes",&s->video_source_bytes,OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(obj,"video-source-seq",&s->video_source_seq,OBJ_PROP_FLAG_READ);
    object_property_add_str(obj,"video-reason",video_reason_get,NULL);
}
