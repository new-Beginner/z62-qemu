/* SPDX-License-Identifier: GPL-2.0-or-later
 * Experimental C1.70 preview bank1 transaction. Statistics bank0 is NOT
 * completed here. Native submitted RAW and output descriptors are required.
 * Pixel filtering is the explicit approximation in preview-pixels.h.
 */
#define PREVIEW_DELAY_NS 1000000
#define PREVIEW_CORE_BYTES 0x3000
#define PREVIEW_RAW_BYTES 0x10000

typedef struct Z62PreviewSpan {
    uint64_t address, bytes;
    unsigned channel, frame;
} Z62PreviewSpan;

static bool preview_supported(NikonZ72BootConfig *s)
{
    return s->z62_preview && s->z62_card_detect && s->master_role && s->preview_mapped;
}

static void preview_irq99(NikonZ72BootConfig *s)
{
    if (s->intc && preview_supported(s)) {
        qemu_set_irq(qdev_get_gpio_in(s->intc, 99-32),
            (s->preview_raw[0x20/4] & s->preview_raw[0x24/4]) != 0);
    }
}

static char *preview_reason_get(Object *obj, Error **errp)
{
    NikonZ72BootConfig *s = NIKON_Z72_BOOT_CONFIG(obj);
    static const char *const names[] = {"reset", "source", "geometry-or-format",
        "destination", "not-ram", "overlap", "dma-error", "configuration-changed", "success", "drain"};
    return g_strdup(s->preview_reason < G_N_ELEMENTS(names) ? names[s->preview_reason] : "invalid");
}

static bool preview_ram(NikonZ72BootConfig *s, uint64_t address, uint64_t bytes, bool write)
{
    if (!bytes || address > UINT32_MAX || bytes > UINT32_MAX || address+bytes > UINT64_C(0x100000000)) { return false; }
    hwaddr translated, available = bytes;
    MemoryRegion *mr = address_space_translate(&s->preview_memory, address,
        &translated, &available, write, MEMTXATTRS_UNSPECIFIED);
    MemoryRegion *root = s->root ? s->root : get_system_memory();
    MemoryRegionSection part = memory_region_find(root, address, bytes);
    bool valid = part.mr && part.mr == mr && memory_region_is_ram(mr) &&
        !memory_region_is_rom(mr) && (!write || !part.readonly) &&
        available >= bytes && int128_ge(part.size, int128_make64(bytes));
    if (part.mr) { memory_region_unref(part.mr); }
    return valid;
}

static bool preview_pool(uint64_t address, uint64_t bytes)
{
    static const uint64_t pools[][2] = {
        {0x8d000000,0xbed17000}, {0xbf700000,0xbff24a00},
        {0xcea00000,0xd4dcb400}, {0xd4e00000,0xdd63b000}, {0xdd700000,0xfffc2800}
    };
    for (unsigned i=0;i<G_N_ELEMENTS(pools);i++) {
        if (address>=pools[i][0] && address+bytes<=pools[i][1]) { return true; }
    }
    return false;
}

static bool preview_ready(NikonZ72BootConfig *s)
{
    return preview_supported(s) && !s->preview_stopping && s->preview_source_valid &&
        s->preview_source_seq > s->preview_last_seq &&
        (ldl_le_p(s->transfer_table+4)&1) &&
        (s->preview_raw[8/4]&1) && (s->preview_core[0x2100/4]&1) &&
        (s->preview_core[0x2608/4]&1);
}

static void preview_schedule(NikonZ72BootConfig *s)
{
    if (!preview_ready(s) || timer_pending(s->preview_timer)) { return; }
    /* Leave unacknowledged output intact, including masked completions. */
    if ((ldl_le_p(s->transfer_table+0x20)&8) || (s->preview_raw[0x24/4]&0x1002)) {
        s->preview_blocked++; return;
    }
    timer_mod(s->preview_timer,qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL)+PREVIEW_DELAY_NS);
}

static void preview_source_notify(NikonZ72BootConfig *s)
{
    if (!preview_supported(s)) { return; }
    uint8_t word[4], descriptors[16];
    if (address_space_read(&s->preview_memory,0x20069a3c,MEMTXATTRS_UNSPECIFIED,word,4)!=MEMTX_OK ||
        address_space_read(&s->preview_memory,0x20069a50+(ldl_le_p(word)&1)*16,
            MEMTXATTRS_UNSPECIFIED,descriptors,16)!=MEMTX_OK) {
        s->preview_source_valid=false; s->preview_reason=1; return;
    }
    for(unsigned i=0;i<4;i++) { s->preview_source[i]=ldl_le_p(descriptors+i*4); }
    s->preview_source_seq=s->raw_stream_frames;
    s->preview_source_valid=true;
    preview_schedule(s);
}

static bool preview_span_add(Z62PreviewSpan *spans, unsigned *count, uint64_t address,
                             uint64_t bytes, unsigned channel, unsigned frame)
{
    for(unsigned i=0;i<*count;i++) {
        Z62PreviewSpan *other=&spans[i];
        if(address<other->address+other->bytes && other->address<address+bytes &&
           !(other->frame!=frame && other->channel==channel && other->address==address && other->bytes==bytes)) {
            return false;
        }
    }
    spans[(*count)++]=(Z62PreviewSpan){address,bytes,channel,frame};
    return true;
}

static void preview_tick(void *opaque)
{
    NikonZ72BootConfig *s=opaque;
    if(!preview_ready(s)) { return; }
    s->preview_attempts++;
    g_autofree uint8_t *raw=NULL;
    uint32_t src[4],dst[4][3],w[3],h[3],stride[3],uv_offset[3];
    Z62PreviewSpan spans[24]; unsigned span_count=0;
    uint32_t reason=2;
    if(s->preview_raw[0x48/4]!=0x05ea03ee || s->preview_raw[0x30c/4]!=Z62_PREVIEW_STRIDE ||
       s->preview_raw[0x300/4]!=0 || s->preview_core[0x2100/4]!=0x121 ||
       s->preview_core[0x2600/4]!=0x305 || s->preview_core[0x2604/4]!=1002) { goto rejected; }
    for(unsigned channel=0;channel<3;channel++) {
        uint32_t *r=&s->preview_core[(0x400+(channel+3)*0x40)/4];
        w[channel]=r[8]&0x7fff; h[channel]=r[8]>>16; stride[channel]=r[4]; uv_offset[channel]=r[10];
        if(r[0]!=0x09000201 || (r[8]&0x8000) || !w[channel] || !h[channel] ||
           (w[channel]&1) || (h[channel]&1) || w[channel]>1920 || h[channel]>1080 ||
           stride[channel]<w[channel] || stride[channel]>2048 || r[5]!=stride[channel] ||
           uv_offset[channel]<(uint64_t)stride[channel]*h[channel]) { goto rejected; }
    }
    for(unsigned frame=0;frame<4;frame++) {
        src[frame]=s->preview_raw[0x310/4+frame];
        bool supplied=false;
        for(unsigned i=0;i<4;i++) { supplied |= src[frame]==s->preview_source[i]; }
        reason=1;
        if(!supplied || src[frame]<0x82c00000 || (uint64_t)src[frame]+Z62_PREVIEW_RAW_BYTES>0x8aebc400) { goto rejected; }
        reason=4;
        if(!preview_ram(s,src[frame],Z62_PREVIEW_RAW_BYTES,false)) { goto rejected; }
        for(unsigned channel=0;channel<3;channel++) {
            dst[frame][channel]=s->preview_core[0x2200/4+frame*16+channel+3];
            uint64_t y=dst[frame][channel],uv=y+uv_offset[channel];
            uint64_t ybytes=(uint64_t)stride[channel]*h[channel],uvbytes=ybytes/2;
            reason=3;
            if((y&15) || !preview_pool(y,ybytes) || !preview_pool(uv,uvbytes)) { goto rejected; }
            reason=4;
            if(!preview_ram(s,y,ybytes,true) || !preview_ram(s,uv,uvbytes,true)) { goto rejected; }
            reason=5;
            if(!preview_span_add(spans,&span_count,y,ybytes,channel,frame) ||
               !preview_span_add(spans,&span_count,uv,uvbytes,channel,frame)) { goto rejected; }
        }
    }
    /* All four RAW inputs and twelve outputs were checked before any write. */
    if(!s->preview_pixels) { s->preview_pixels=z62_preview_pixels_new(); }
    raw=g_malloc(Z62_PREVIEW_RAW_BYTES);
    for(unsigned frame=0;frame<4;frame++) {
        reason=6;
        if(address_space_read(&s->preview_memory,src[frame],MEMTXATTRS_UNSPECIFIED,raw,Z62_PREVIEW_RAW_BYTES)!=MEMTX_OK) { goto rejected; }
        z62_preview_pixels_input(s->preview_pixels,raw);
        for(unsigned channel=0;channel<3;channel++) {
            const uint8_t *pixels=z62_preview_pixels_render(s->preview_pixels,channel,w[channel],h[channel],stride[channel]);
            size_t ybytes=(size_t)stride[channel]*h[channel];
            uint64_t address=dst[frame][channel];
            if(!pixels || address_space_write(&s->preview_memory,address,MEMTXATTRS_UNSPECIFIED,pixels,ybytes)!=MEMTX_OK ||
               address_space_write(&s->preview_memory,address+uv_offset[channel],MEMTXATTRS_UNSPECIFIED,pixels+ybytes,ybytes/2)!=MEMTX_OK) { goto rejected; }
            s->preview_bytes+=ybytes+ybytes/2;
            s->preview_outputs++;
        }
    }
    s->preview_last_seq=s->preview_source_seq;
    s->preview_batches++;
    s->preview_reason=8;
    /* Only preview command bank1 completed. Bank0's statistics were not run. */
    stl_le_p(s->transfer_table+0x20,ldl_le_p(s->transfer_table+0x20)|8);
    transfer_update_irq(s);
    s->preview_raw[0x24/4]|=0x1002;
    preview_irq99(s);
    return;
rejected:
    s->preview_reason=reason;
    s->preview_rejected++;
    /* Do not retry a failed source batch just because software polls controls. */
    s->preview_last_seq=s->preview_source_seq;
}

static void preview_drain_tick(void *opaque)
{
    NikonZ72BootConfig *s=opaque;
    if(!preview_supported(s)) { return; }
    if(s->preview_flush_pending) {
        s->preview_flush_pending=false;
        uint32_t *r=s->preview_raw;
        /* Native1036C14E's single-instance dummy read flushes a stopped pipe. */
        if(r[8/4]!=1 || r[0x48/4]!=0x0014000e || r[0x300/4]!=2 ||
           r[0x30c/4]!=32 || r[0x3e8/4]!=2 || r[0x410/4] || r[0x420/4]) { return; }
        uint8_t data[448];
        if(!preview_ram(s,r[0x310/4],sizeof(data),false) ||
           address_space_read(&s->preview_memory,r[0x310/4],MEMTXATTRS_UNSPECIFIED,data,sizeof(data))!=MEMTX_OK) {
            s->preview_reason=6; return;
        }
        s->preview_raw[0x24/4]|=2;
        s->preview_flushes++;
        preview_irq99(s);
    } else if(s->preview_drain_mask==15) {
        s->preview_drain_mask=0;
        s->preview_raw[8/4]&=~1u;
        s->preview_raw[0x24/4]|=0x014a0000;
        s->preview_drains++;
        s->preview_reason=9;
        preview_irq99(s);
    }
}

static void preview_cancel(NikonZ72BootConfig *s)
{
    if(timer_pending(s->preview_timer)) { s->preview_cancelled++; }
    timer_del(s->preview_timer);
}

static bool preview_unit_status(unsigned offset)
{
    /* Only the physical units in the observed 18-node preview graph. */
    static const unsigned units[]={0xe60,0x900,0xde0,0x8a0,0x8c0,0x8e0,0x9e0,0x940,0xba0,0x920};
    for(unsigned i=0;i<G_N_ELEMENTS(units);i++) { if(offset==units[i]) { return true; } }
    return false;
}

static uint64_t preview_core_read(void *opaque, hwaddr offset, unsigned size)
{
    NikonZ72BootConfig *s=opaque;
    if(offset<0x100) { return transfer_read(s,offset,size); }
    if(preview_unit_status(offset)) { return timer_pending(s->preview_timer) ? 3:0; }
    return s->preview_core[offset/4];
}

static void preview_core_write(void *opaque, hwaddr offset, uint64_t value, unsigned size)
{
    NikonZ72BootConfig *s=opaque;
    if(offset<0x100) {
        if(offset==4 && !(value&1)) { preview_cancel(s); }
        transfer_write(s,offset,value,size);
    } else {
        if(s->preview_core[offset/4]!=(uint32_t)value) { preview_cancel(s); }
        s->preview_core[offset/4]=value;
    }
    preview_schedule(s);
}

static uint64_t preview_raw_read(void *opaque, hwaddr offset, unsigned size)
{
    NikonZ72BootConfig *s=opaque;
    return s->preview_raw[offset/4];
}

static void preview_raw_write(void *opaque, hwaddr offset, uint64_t value, unsigned size)
{
    NikonZ72BootConfig *s=opaque;
    if(offset==0x24) { s->preview_raw[offset/4]&=~(uint32_t)value; }
    else {
        if(offset!=0x20 && s->preview_raw[offset/4]!=(uint32_t)value) { preview_cancel(s); }
        s->preview_raw[offset/4]=value;
        if(offset==0xf0 && value==0xfc400) {
            s->preview_drain_mask=0;
            s->preview_stopping=true;
            s->preview_last_seq=s->preview_source_seq;
            preview_cancel(s);
        }
        if(s->preview_raw[0xf0/4]==0xfc400 && value==1 &&
           (offset==0x54 || offset==0x60 || offset==0x6c || offset==0x78)) {
            s->preview_drain_mask|=1u<<((offset-0x54)/12);
            if(s->preview_drain_mask==15) {
                preview_cancel(s);
                timer_mod(s->preview_drain_timer,qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL)+PREVIEW_DELAY_NS);
            }
        }
        if(offset==8 && value==1 && s->preview_raw[0x48/4]==0x0014000e) {
            s->preview_flush_pending=true;
            timer_mod(s->preview_drain_timer,qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL)+PREVIEW_DELAY_NS);
        }
        if(offset==8 && value==1 && s->preview_raw[0x48/4]==0x05ea03ee) {
            s->preview_stopping=false;
            s->preview_drain_mask=0;
            s->preview_flush_pending=false;
            timer_del(s->preview_drain_timer);
        }
    }
    preview_irq99(s);
    preview_schedule(s);
}

static const MemoryRegionOps preview_core_ops={
    .read=preview_core_read,.write=preview_core_write,.endianness=DEVICE_LITTLE_ENDIAN,
    .valid={.min_access_size=4,.max_access_size=4},.impl={.min_access_size=4,.max_access_size=4}
};
static const MemoryRegionOps preview_raw_ops={
    .read=preview_raw_read,.write=preview_raw_write,.endianness=DEVICE_LITTLE_ENDIAN,
    .valid={.min_access_size=4,.max_access_size=4},.impl={.min_access_size=4,.max_access_size=4}
};

static void preview_reset(NikonZ72BootConfig *s)
{
    timer_del(s->preview_timer); timer_del(s->preview_drain_timer);
    s->preview_source_valid=s->preview_flush_pending=s->preview_stopping=false;
    s->preview_source_seq=s->preview_last_seq=0;
    s->preview_drain_mask=s->preview_reason=0;
    memset(s->preview_core,0,sizeof(s->preview_core));
    memset(s->preview_raw,0,sizeof(s->preview_raw));
    memset(s->preview_source,0,sizeof(s->preview_source));
    s->preview_attempts=s->preview_batches=s->preview_outputs=s->preview_bytes=0;
    s->preview_rejected=s->preview_blocked=s->preview_cancelled=s->preview_drains=s->preview_flushes=0;
    z62_preview_pixels_free(s->preview_pixels); s->preview_pixels=NULL;
    preview_irq99(s);
}

static void preview_init(Object *obj)
{
    NikonZ72BootConfig *s=NIKON_Z72_BOOT_CONFIG(obj);
    s->preview_timer=timer_new_ns(QEMU_CLOCK_VIRTUAL,preview_tick,s);
    s->preview_drain_timer=timer_new_ns(QEMU_CLOCK_VIRTUAL,preview_drain_tick,s);
    object_property_add_uint64_ptr(obj,"preview-attempts",&s->preview_attempts,OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(obj,"preview-batches",&s->preview_batches,OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(obj,"preview-outputs",&s->preview_outputs,OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(obj,"preview-bytes",&s->preview_bytes,OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(obj,"preview-rejected",&s->preview_rejected,OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(obj,"preview-blocked",&s->preview_blocked,OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(obj,"preview-cancelled",&s->preview_cancelled,OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(obj,"preview-drains",&s->preview_drains,OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(obj,"preview-flushes",&s->preview_flushes,OBJ_PROP_FLAG_READ);
    object_property_add_str(obj,"preview-reason",preview_reason_get,NULL);
}

static void preview_realize(NikonZ72BootConfig *s, MemoryRegion *root)
{
    if(!s->z62_preview || !s->master_role || !s->z62_card_detect) { return; }
    address_space_init(&s->preview_memory,root,"z62-preview-dma");
    memory_region_init_io(&s->preview_core_mr,OBJECT(s),&preview_core_ops,s,"z62-preview-core",PREVIEW_CORE_BYTES);
    memory_region_init_io(&s->preview_raw_mr,OBJECT(s),&preview_raw_ops,s,"z62-preview-raw",PREVIEW_RAW_BYTES);
    memory_region_add_subregion_overlap(root,0x20100000,&s->preview_core_mr,2);
    memory_region_add_subregion_overlap(root,0x20380000,&s->preview_raw_mr,2);
    s->preview_mapped=true;
}

static void preview_finalize(NikonZ72BootConfig *s)
{
    timer_del(s->preview_timer); timer_free(s->preview_timer);
    timer_del(s->preview_drain_timer); timer_free(s->preview_drain_timer);
    z62_preview_pixels_free(s->preview_pixels);
    if(s->preview_mapped) {
        MemoryRegion *root=s->root ? s->root:get_system_memory();
        memory_region_del_subregion(root,&s->preview_core_mr);
        memory_region_del_subregion(root,&s->preview_raw_mr);
        address_space_destroy(&s->preview_memory);
    }
}
