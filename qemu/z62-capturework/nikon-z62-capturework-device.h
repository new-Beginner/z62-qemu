/* SPDX-License-Identifier: GPL-2.0-or-later
 * Default-off C capture backend. Qualified original control writes freeze
 * configuration; an explicit MAIN publication supplies pixels. Only real,
 * preflighted DMA can publish front3/4 and packed135. No guest software writes.
 */
#include "block/thread-pool.h"
#include "block/aio-wait.h"
#include "migration/blocker.h"
#include "nikon-z62-capturework-api.h"

enum { CW_RESET, CW_IDLE, CW_SOURCE, CW_CONFIG, CW_ADDRESS, CW_ALIAS,
       CW_RAM, CW_BACKPRESSURE, CW_COMPUTE, CW_IO, CW_SUCCESS, CW_EXHAUSTED };
static const unsigned cw_geometry[] = {0x1d00,0x1d04,0x1e78,0x1e7c,0x1f00};
static const unsigned cw_buffers[] = {0x1a08,0x1a14,0x1a18,0x1a24,0x1a3c,
    0x1a40,0x1a44,0x1a48,0x1a4c,0x1a50,0x1a54,0x1a58,0x1a5c,
    0x1a60,0x1a64,0x1a68,0x1a6c,0x1a80};
static void cw_start(Z72InputConfig *s);

static void cw_task_free(Z72InputConfig *s)
{
    Z62CWTask *task=s->cw.task;
    if (!task) return;
    g_assert(!task->submitted || task->ready);
    s->cw.task=NULL;
    z62_main_source_release(&s->cw.source,&task->lease);
    g_free(task->input); g_free(task->packed); g_free(task);
    object_unref(OBJECT(s));
}

static void cw_cancel(Z72InputConfig *s)
{
    Z62CaptureWork *c=&s->cw;
    timer_del(c->timer);
    if (c->generation<UINT64_MAX) c->generation++; else c->reason=CW_EXHAUSTED;
    if (c->task) c->cancelled++;
    c->output_valid=false;
    if (c->source.valid) c->last_publication=c->source.meta.publication;
    z62_main_source_cancel(&c->source);
    if (c->task && (!c->task->submitted || c->task->ready)) cw_task_free(s);
}

static bool cw_copy_known(Z72InputConfig *s,unsigned offset,uint32_t *destination)
{
    if (!s->cw.known[offset/4]) return false;
    *destination=s->registers[offset/4];
    return true;
}

static void cw_commit(Z72InputConfig *s,uint32_t selected)
{
    Z62CaptureWork *c=&s->cw;
    Z62CWProfile prior=c->profile;
    bool validity[3]; memcpy(validity,c->valid,sizeof(validity));
    if (selected&1) c->valid[0]=cw_copy_known(s,0x500,&c->profile.correction);
    if (selected&4) {
        bool valid=true;
        for (unsigned i=0;i<G_N_ELEMENTS(cw_geometry);i++) valid&=cw_copy_known(s,cw_geometry[i],&c->profile.geometry[i]);
        c->valid[1]=valid;
    }
    if (selected&0x80) {
        bool valid=true;
        for (unsigned i=0;i<7;i++) valid&=cw_copy_known(s,0x1514+4*i,&c->profile.packing[i]);
        /* External C MAIN policy0 does not consume the optional shared9530
         * pair. Do not manufacture a write-provenance requirement for it. */
        c->profile.packing[7]=c->known[0x1530/4]?s->registers[0x1530/4]:0;
        for (unsigned i=0;i<G_N_ELEMENTS(cw_buffers);i++) valid&=cw_copy_known(s,cw_buffers[i],&c->profile.buffers[i]);
        if (c->profile.packing[0]&4) {
            for (unsigned i=0;i<128;i++) {
                valid&=c->known[(0x1600+4*i)/4];
                c->profile.lookup[2*i]=(uint16_t)s->registers[(0x1600+4*i)/4];
                c->profile.lookup[2*i+1]=(uint16_t)(s->registers[(0x1600+4*i)/4]>>16);
            }
        } else {
            memset(c->profile.lookup,0,sizeof(c->profile.lookup));
        }
        c->valid[2]=valid;
        /* Bit0 is the separately programmed Z62 bank selector, not part of
         * the BFI #1,#2 parameter. Sample it into each admitted job below. */
        c->profile.buffers[4]&=~1u;
    }
    if (memcmp(&prior,&c->profile,sizeof(prior)) || memcmp(validity,c->valid,sizeof(validity))) {
        c->cursor=c->profile.buffers[6]; cw_cancel(s);
    }
}

/* Full selected ring preflight in the engine-local address space, including
 * canonical backing aliases, readonly and complete-span checks. */
static unsigned cw_ring(Z72InputConfig *s,Z62CWTask *task)
{
    const uint32_t *b=task->profile.buffers;
    MemoryRegion *backing[4]; hwaddr translated[4];
    uint64_t span=task->packed_bytes;
    for (unsigned i=0;i<=b[7];i++) {
        uint64_t address=b[9+4*task->bank+i]; hwaddr available=span;
        if ((address&15) || address<RAW_POOL_START || address+span>RAW_POOL_END) return CW_ADDRESS;
        MemoryRegion *mr=address_space_translate(&s->raw_memory,address,&translated[i],&available,true,MEMTXATTRS_UNSPECIFIED);
        MemoryRegionSection section=memory_region_find(s->raw_root,address,span);
        bool valid=section.mr && section.mr==mr && !section.readonly && memory_region_is_ram(mr) &&
            !memory_region_is_rom(mr) && available>=span && int128_ge(section.size,int128_make64(span));
        if (section.mr) memory_region_unref(section.mr);
        if (!valid) return CW_RAM;
        backing[i]=mr;
        for (unsigned j=0;j<i;j++) if (backing[j]==mr && translated[i]<translated[j]+span &&
            translated[j]<translated[i]+span) return CW_ALIAS;
    }
    task->destination=b[9+4*task->bank+task->slot];
    return 0;
}

static unsigned cw_profile(Z72InputConfig *s,Z62CWTask *task)
{
    const uint32_t *g=task->profile.geometry,*p=task->profile.packing,*b=task->profile.buffers;
    if (task->profile.correction || g[4]!=0x11 || ((g[0]|g[1]|g[2]|g[3]|p[1]|p[2])&0xffff) ||
        (p[0]&~7u) || (p[0]&3)>2 || p[3] || p[4] || p[5] || p[6]!=2 || p[7] ||
        b[1]!=1 || b[2]!=1 || b[3] || b[4] || b[5]!=1 || b[7]>3 || b[6]>b[7] ||
        task->slot>b[7] || b[8] || b[17] || task->lease.meta.width!=(g[1]>>16) ||
        task->lease.meta.height!=(g[0]>>16)) return CW_CONFIG;
    Z62CaptureWorkPixelsConfig *q=&task->pixels;
    *q=(Z62CaptureWorkPixelsConfig){.input_width=g[1]>>16,.input_height=g[0]>>16,
        .input_stride=task->lease.meta.stride,.intermediate_width=g[3]>>16,.intermediate_height=g[2]>>16,
        .output_width=p[1]>>16,.output_height=p[2]>>16,.output_stride=b[0],
        .bits=(p[0]&3)==0?16:(p[0]&3)==1?14:12,.cfa=1,.use_lut=!!(p[0]&4)};
    if (b[0]!=((q->output_width*q->bits/8+15)&~15u)) return CW_CONFIG;
    if (z62_transfer_snapshot(&task->transfer,q->bits,q->use_lut,
        q->use_lut?task->transfer.lookup:NULL)!=Z62_TRANSFER_OK) return CW_CONFIG;
    q->lookup=task->transfer.lookup;
    Z62CaptureWorkPixelsPlan plan;
    uint64_t bytes=(uint64_t)b[0]*q->output_height;
    if (bytes>SIZE_MAX || z62_capturework_pixels_plan(q,task->lease.meta.bytes,(size_t)bytes,&plan)!=Z62_CW_PIXELS_OK) return CW_CONFIG;
    task->packed_bytes=plan.output_span; task->row_bytes=plan.output_row_bytes;
    return cw_ring(s,task);
}

static int cw_compute(void *opaque)
{
    Z62CWTask *task=opaque;
    task->packed=g_malloc(task->packed_bytes);
    memset(task->packed,0xa5,task->packed_bytes);
    return z62_capturework_pixels_pack(&task->pixels,task->input,task->lease.meta.bytes,
        task->packed,task->packed_bytes)==Z62_CW_PIXELS_OK?0:-1;
}

static void cw_computed(void *opaque,int result)
{
    Z62CWTask *task=opaque; Z72InputConfig *s=task->owner;
    task->ready=true; task->success=result==0;
    if (s->cw.stopping || task->generation!=s->cw.generation) {
        object_ref(OBJECT(s)); cw_task_free(s);
        if (!s->cw.stopping) cw_start(s);
        object_unref(OBJECT(s)); return;
    }
    /* The callback never writes guest RAM. A virtual-time event owns DMA. */
    timer_mod(s->cw.timer,qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL));
}

static void cw_tick(void *opaque)
{
    Z72InputConfig *s=opaque; Z62CaptureWork *c=&s->cw; Z62CWTask *task=c->task;
    if (!task || c->stopping || task->generation!=c->generation) return;
    if (!task->submitted) {
        task->submitted=true; thread_pool_submit_aio(cw_compute,task,cw_computed,task); return;
    }
    g_assert(task->ready);
    if (!task->success || c->pending_front || c->pending_raw || cw_ring(s,task)) {
        c->reason=CW_COMPUTE; c->rejected++; cw_task_free(s); return;
    }
    for (uint32_t y=0;y<task->pixels.output_height;y++) {
        if (address_space_write(&s->raw_memory,(uint64_t)task->destination+(uint64_t)y*task->pixels.output_stride,
            MEMTXATTRS_UNSPECIFIED,task->packed+(size_t)y*task->pixels.output_stride,task->row_bytes)!=MEMTX_OK) {
            c->reason=CW_IO; c->rejected++; cw_task_free(s); return;
        }
    }
    uint64_t generation=c->generation;
    c->completed++; c->bytes+=(uint64_t)task->row_bytes*task->pixels.output_height;
    c->output_meta=task->lease.meta; c->output_transfer=task->transfer; c->output_valid=true;
    c->output_address=task->destination; c->output_width=task->pixels.output_width;
    c->output_height=task->pixels.output_height; c->output_stride=task->pixels.output_stride;
    c->output_slot=task->slot; c->output_bank=task->bank;
    c->cursor=(task->slot+1)%(task->profile.buffers[7]+1);
    c->reason=CW_SUCCESS; c->pending_front=0x18; c->pending_raw=0x80;
    object_ref(OBJECT(s)); cw_task_free(s);
    for (unsigned i=0;i<3 && c->generation==generation;i++) qemu_irq_pulse(c->complete[i]);
    object_unref(OBJECT(s));
}

static void cw_start(Z72InputConfig *s)
{
    Z62CaptureWork *c=&s->cw;
    if (!c->enabled || c->stopping || c->task || c->generation==UINT64_MAX) return;
    if (!c->valid[0] || !c->valid[1] || !c->valid[2] || (c->held&0x20d) ||
        (c->allowed&c->running&0x20d)!=0x20d) { c->reason=CW_CONFIG; return; }
    if (c->pending_front || c->pending_raw) { c->reason=CW_BACKPRESSURE; c->blocked++; return; }
    if (!c->source.valid || c->source.meta.publication<=c->last_publication) { c->reason=CW_SOURCE; return; }
    Z62CWTask *task=g_new0(Z62CWTask,1);
    z62_main_source_start(&c->source);
    if (z62_main_source_begin(&c->source,&task->lease)!=Z62_MAIN_OK) { g_free(task); c->reason=CW_SOURCE; return; }
    task->owner=s; task->generation=c->generation; task->profile=c->profile;
    task->slot=c->cursor; task->bank=s->registers[0x1a3c/4]&1;
    if (task->profile.packing[0]&4) memcpy(task->transfer.lookup,task->profile.lookup,sizeof(task->transfer.lookup));
    unsigned why=cw_profile(s,task);
    if (why) { c->reason=why; c->rejected++; z62_main_source_release(&c->source,&task->lease); g_free(task); return; }
    /* Private data for off-BQL compute; cancellation may release/reuse the
     * external mailbox without changing this job's input or transfer. */
    task->input=g_memdup2(task->lease.pixels,task->lease.meta.bytes);
    c->last_publication=task->lease.meta.publication; c->output_valid=false;
    c->task=task; object_ref(OBJECT(s));
    timer_mod(c->timer,qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL)+1000000);
}

void z62_capturework_control(DeviceState *dev,hwaddr address,uint32_t value)
{
    if (!dev) return;
    Z72InputConfig *s=Z72_INPUT_CONFIG(dev); Z62CaptureWork *c=&s->cw;
    if (!c->enabled || !s->z62_layout) return;
    if (address==0x20068100 || address==0x20068104) cw_commit(s,value);
    else if (address==0x20068000) { c->held|=value&0xfff; if (value&0x20d) cw_cancel(s); }
    else if (address==0x20068004) c->held&=~value;
    else if (address==0x20068010) c->allowed|=value&0xfff;
    else if (address==0x20068014) { c->allowed&=~value; c->running&=~value; if (value&0x20d) cw_cancel(s); }
    else if (address==0x20068008) c->running|=value&0xfff;
    else if (address==0x2006800c) { c->running&=~value; if (value&0x20d) cw_cancel(s); }
    else if (address==0x20068210) c->pending_front&=~value;
    else if (address==0x20068290) c->pending_raw&=~value;
    else return;
    cw_start(s);
}

static void cw_file_set(Object *obj,const char *path,Error **errp)
{
    Z72InputConfig *s=Z72_INPUT_CONFIG(obj); Z62CaptureWork *c=&s->cw;
    GStatBuf info;
    if (!c->enabled || c->stopping || c->source.leased || strlen(path)>4096 ||
        !g_str_is_ascii(path) || !g_path_is_absolute(path) || path[0]=='\\' ||
        g_stat(path,&info) || !S_ISREG(info.st_mode) || info.st_size<96 || info.st_size>Z62_MAIN_MAX_BYTES+96) {
        error_setg(errp,"Enabled idle CaptureWork needs a bounded ordinary ASCII MAIN file"); return;
    }
    FILE *file=g_fopen(path,"rb");
    if (!file) { error_setg_errno(errp,errno,"Cannot open MAIN source"); return; }
    g_autofree uint8_t *packet=g_malloc(info.st_size);
    bool complete=fread(packet,1,info.st_size,file)==info.st_size && fgetc(file)==EOF && !ferror(file);
    fclose(file); Z62MainMetadata meta;
    if (!complete || z62_main_parse(packet,info.st_size,&meta)!=Z62_MAIN_OK) {
        error_setg(errp,"Invalid MAIN source envelope"); return;
    }
    if (!c->source.pixels) {
        z62_main_source_init(&c->source,g_malloc(meta.bytes),meta.bytes);
    } else if (meta.bytes>c->source.capacity) {
        c->source.pixels=g_realloc(c->source.pixels,meta.bytes); c->source.capacity=meta.bytes;
    }
    if (z62_main_source_publish(&c->source,packet,info.st_size)!=Z62_MAIN_OK) {
        error_setg(errp,"MAIN source publication rejected"); return;
    }
    cw_start(s);
}

static char *cw_status_get(Object *obj,Error **errp)
{
    Z62CaptureWork *c=&Z72_INPUT_CONFIG(obj)->cw;
    static const char *const reasons[]={"reset","idle","source-missing-or-old","configuration",
        "address","alias","not-writable-ram","backpressure","compute","dma-error","success","generation-exhausted"};
    GString *out=g_string_new(NULL);
    g_string_append_printf(out,"{\"enabled\":%s,\"active\":%s,\"valid\":%s,\"reason\":\"%s\","
        "\"generation\":%" PRIu64 ",\"completed\":%" PRIu64 ",\"rejected\":%" PRIu64 ","
        "\"cancelled\":%" PRIu64 ",\"blocked\":%" PRIu64 ",\"bytes\":%" PRIu64 ","
        "\"pending_front\":%u,\"pending_raw\":%u,\"address\":%u,\"width\":%u,\"height\":%u,"
        "\"stride\":%u,\"slot\":%u,\"bank\":%u,\"epoch\":%" PRIu64 ",\"publication\":%" PRIu64 ","
        "\"frame\":%" PRIu64 ",\"time_ns\":%" PRIu64 ",\"bits\":%u,\"codec\":%u,\"lookup\":[",
        c->enabled?"true":"false",c->task?"true":"false",c->output_valid?"true":"false",
        c->reason<G_N_ELEMENTS(reasons)?reasons[c->reason]:"invalid",c->generation,c->completed,c->rejected,
        c->cancelled,c->blocked,c->bytes,c->pending_front,c->pending_raw,c->output_address,c->output_width,
        c->output_height,c->output_stride,c->output_slot,c->output_bank,c->output_meta.epoch,
        c->output_meta.publication,c->output_meta.frame,c->output_meta.time_ns,c->output_transfer.bits,c->output_transfer.codec);
    for (unsigned i=0;i<256;i++) g_string_append_printf(out,"%s%u",i?",":"",c->output_transfer.lookup[i]);
    g_string_append(out,"]}"); return g_string_free(out,false);
}

static void cw_reset(Z72InputConfig *s)
{
    Z62CaptureWork *c=&s->cw; cw_cancel(s);
    memset(c->known,0,sizeof(c->known)); memset(c->valid,0,sizeof(c->valid)); memset(&c->profile,0,sizeof(c->profile));
    c->held=c->allowed=c->running=c->cursor=c->pending_front=c->pending_raw=0;
    c->completed=c->rejected=c->cancelled=c->blocked=c->bytes=0; c->reason=CW_RESET;
    z62_main_source_reset(&c->source);
    for (unsigned i=0;i<3;i++) qemu_set_irq(c->complete[i],0);
}

static void cw_init(Object *obj)
{
    Z72InputConfig *s=Z72_INPUT_CONFIG(obj);
    s->cw.generation=1; s->cw.timer=timer_new_ns(QEMU_CLOCK_VIRTUAL,cw_tick,s);
    object_property_add_str(obj,"capturework-main-file",NULL,cw_file_set);
    object_property_add_str(obj,"capturework-status",cw_status_get,NULL);
    qdev_init_gpio_out_named(DEVICE(obj),s->cw.complete,"capturework-complete",3);
}

static void cw_realize(DeviceState *dev,Error **errp)
{
    Z72InputConfig *s=Z72_INPUT_CONFIG(dev); Error *local_error=NULL;
    raw_realize(dev,&local_error);
    if (local_error) { error_propagate(errp,local_error); return; }
    if (!s->cw.enabled) return;
    if (!s->z62_layout || !s->raw_root) { error_setg(errp,"CaptureWork requires Z62 engine-local RAM"); return; }
    error_setg(&s->cw.migration_blocker,"Experimental Z62 CaptureWork does not yet support complete snapshots");
    migrate_add_blocker(&s->cw.migration_blocker,errp);
}

static void cw_unrealize(DeviceState *dev)
{
    Z72InputConfig *s=Z72_INPUT_CONFIG(dev); s->cw.stopping=true; cw_cancel(s);
    AIO_WAIT_WHILE(qemu_get_aio_context(),s->cw.task!=NULL);
    migrate_del_blocker(&s->cw.migration_blocker);
    g_clear_pointer(&s->cw.source.pixels,g_free); raw_unrealize(dev);
}

static void cw_finalize(Object *obj)
{ timer_free(Z72_INPUT_CONFIG(obj)->cw.timer); }
