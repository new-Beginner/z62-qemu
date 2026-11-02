/* SPDX-License-Identifier: GPL-2.0-or-later
 * Default-off compound bank0 software ISP. Not Nikon's eleven operators.
 * Source-slot events are private model provenance, emitted after real RGB DMA.
 */
#include "nikon-z62-grid-pixels.h"

static void z62_grid_schedule(NikonZ72BootConfig *s);

static bool z62_grid_supported(NikonZ72BootConfig *s)
{
    return s->z62_grid_process && preview_supported(s);
}

static int z62_grid_slot(uint32_t address)
{
    if (address < 0x88edf000) { return -1; }
    uint32_t delta = address - 0x88edf000;
    if (delta % 0x36000 || delta / 0x36000 >= 6) { return -1; }
    return (int)(delta / 0x36000);
}

static bool z62_grid_pending(NikonZ72BootConfig *s)
{
    return (ldl_le_p(s->transfer_table+0x20)&4) || (ldl_le_p(s->transfer_table+0x1c)&0x10);
}

static bool z62_grid_profile(NikonZ72BootConfig *s)
{
    static const uint32_t ports[2][13] = {
        {0x20121,0,0,0,128,128,128,0,0x28003c,0,0x12000,0x24000,0},
        {0x10621,0,0,0,96,96,0,0,0x28003c,0,0,0,0}
    };
    static const uint32_t body[35] = {
        0x110a0000,0x40000,0,0x10002,0,0,0,0xff000000,0,0,
        0x11080040,0x3b0000,0x270000,0x3c003c,0x20002,0,0,0,
        0x01110080,0,0,0,0xfff,0,0xfff,0,0,0,0,0,0,0,0,0,0
    };
    uint8_t parameter[160];
    const uint32_t *r = &s->preview_core[0x9c0/4];
    if (s->preview_core[0x2000/4] != 0x131 || s->preview_core[0x2640/4] != 0x202 ||
        s->preview_core[0x2644/4] != 40 || s->preview_core[0x2648/4] != 3) { return false; }
    for (unsigned p=0;p<2;p++) {
        for (unsigned i=0;i<13;i++) {
            if (i != 1 && s->preview_core[(0x440+p*0x40)/4+i] != ports[p][i]) { return false; }
        }
    }
    if (r[0] || r[2] != 0x74011 || r[3] != 0x4100 || r[5] || (r[4]&3) ||
        !preview_ram(s,r[4],sizeof(parameter),false) ||
        address_space_read(&s->preview_memory,r[4],MEMTXATTRS_UNSPECIFIED,
                           parameter,sizeof(parameter)) != MEMTX_OK) { return false; }
    for (unsigned i=0;i<G_N_ELEMENTS(body);i++) {
        if (ldl_le_p(parameter+i*4) != body[i]) { return false; }
    }
    /* +8c callback, +90 event and +9c software bookkeeping are not success gates. */
    return ldl_le_p(parameter+0x94) == r[2] && ldl_le_p(parameter+0x98) == r[3];
}

static void z62_grid_tick(void *opaque)
{
    NikonZ72BootConfig *s=opaque;
    g_autofree uint8_t *input=NULL;
    g_autofree uint8_t *packed=NULL;
    uint32_t source[4][3], destination[4], reason=3;
    uint64_t epoch[6];
    int slot[4];
    bool fresh=false;
    if (!z62_grid_supported(s) || !(ldl_le_p(s->transfer_table+4)&1) ||
        s->preview_core[0x2648/4] != 3) { return; }
    if (z62_grid_pending(s)) { s->grid_blocked++; return; }
    s->grid_needs_check=false;
    s->grid_checked_seq=s->grid_source_seq;
    if (!z62_grid_profile(s)) { goto rejected; }
    memcpy(epoch,s->grid_slot_epoch,sizeof(epoch));
    for (unsigned f=0;f<4;f++) {
        source[f][0]=s->preview_core[0x2200/4+f*16+1];
        slot[f]=z62_grid_slot(source[f][0]);
        reason=4;
        if (slot[f] < 0) { goto rejected; }
        if (!(s->grid_supplied_mask & (1u<<slot[f]))) { s->grid_reason=1; return; }
        fresh |= epoch[slot[f]] > s->grid_seen_epoch[slot[f]];
        for (unsigned c=0;c<3;c++) {
            source[f][c]=source[f][0]+c*0x12000;
            reason=6;
            if (!preview_ram(s,source[f][c],Z62_GRID_SRC_BYTES,false)) { goto rejected; }
        }
        destination[f]=s->preview_core[0x2200/4+f*16+2];
        uint64_t start=destination[f], end=start+Z62_GRID_DST_BYTES;
        reason=5;
        if ((start&15) || start<0x8aebc400 || end>0x8d000000) { goto rejected; }
        reason=6;
        if (!preview_ram(s,start,Z62_GRID_DST_BYTES,true)) { goto rejected; }
        reason=7;
        for (unsigned p=0;p<f;p++) {
            if (start<(uint64_t)destination[p]+Z62_GRID_DST_BYTES && destination[p]<end) { goto rejected; }
        }
    }
    if (!fresh) { s->grid_reason=11; return; }
    for (unsigned d=0;d<4;d++) {
        uint64_t start=destination[d],end=start+Z62_GRID_DST_BYTES;
        for (unsigned f=0;f<4;f++) {
            for (unsigned c=0;c<3;c++) {
                if (start<(uint64_t)source[f][c]+Z62_GRID_SRC_BYTES && source[f][c]<end) {
                    reason=7; goto rejected;
                }
            }
        }
    }
    input=g_malloc(4*3*Z62_GRID_SRC_BYTES);
    packed=g_malloc(4*Z62_GRID_DST_BYTES);
    for (unsigned f=0;f<4;f++) {
        for (unsigned c=0;c<3;c++) {
            reason=8;
            if (address_space_read(&s->preview_memory,source[f][c],MEMTXATTRS_UNSPECIFIED,
                    input+(f*3+c)*Z62_GRID_SRC_BYTES,Z62_GRID_SRC_BYTES) != MEMTX_OK) { goto rejected; }
        }
        reason=9;
        if (!z62_grid_convert(input+(f*3)*Z62_GRID_SRC_BYTES,
                              input+(f*3+1)*Z62_GRID_SRC_BYTES,
                              input+(f*3+2)*Z62_GRID_SRC_BYTES,Z62_GRID_SRC_BYTES,
                              packed+f*Z62_GRID_DST_BYTES,Z62_GRID_DST_BYTES)) { goto rejected; }
    }
    /* Every source, destination and numerical result passed before any DMA write. */
    for (unsigned f=0;f<4;f++) {
        reason=8;
        if (address_space_write(&s->preview_memory,destination[f],MEMTXATTRS_UNSPECIFIED,
                packed+f*Z62_GRID_DST_BYTES,Z62_GRID_DST_BYTES) != MEMTX_OK) { goto rejected; }
        s->grid_outputs++; s->grid_bytes+=Z62_GRID_DST_BYTES;
    }
    for (unsigned f=0;f<4;f++) { s->grid_seen_epoch[slot[f]]=epoch[slot[f]]; }
    s->grid_groups++; s->grid_reason=10;
    stl_le_p(s->transfer_table+0x1c,ldl_le_p(s->transfer_table+0x1c)|0x10);
    stl_le_p(s->transfer_table+0x20,ldl_le_p(s->transfer_table+0x20)|4);
    transfer_update_irq(s);
    return;
rejected:
    s->grid_reason=reason; s->grid_rejected++;
}

static void z62_grid_schedule(NikonZ72BootConfig *s)
{
    if (!z62_grid_supported(s) || !(ldl_le_p(s->transfer_table+4)&1) ||
        s->preview_core[0x2648/4] != 3 || timer_pending(s->grid_timer)) { return; }
    if (z62_grid_pending(s)) { s->grid_blocked++; return; }
    if (!s->grid_needs_check && s->grid_source_seq == s->grid_checked_seq) { return; }
    timer_mod(s->grid_timer,qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL)+1000000);
}

static void z62_grid_source(void *opaque,int line,int level)
{
    NikonZ72BootConfig *s=opaque;
    if (!s->z62_grid_process || !s->master_role || line<0 || line>=6) { return; }
    uint8_t bit=1u<<line;
    bool edge=level && !(s->grid_level_mask&bit);
    if (level) { s->grid_level_mask|=bit; } else { s->grid_level_mask&=~bit; }
    if (!edge) { return; }
    s->grid_slot_epoch[line]=++s->grid_source_seq;
    s->grid_supplied_mask|=bit;
    z62_grid_schedule(s);
}

static bool z62_grid_config_address(unsigned offset)
{
    return (offset>=0x440 && offset<0x4b4) || (offset>=0x9c0 && offset<0x9d8) ||
           (offset>=0x2000 && offset<0x203c) || (offset>=0x2640 && offset<=0x2648) ||
           (offset>=0x2200 && offset<0x2300 && ((offset&63)==4 || (offset&63)==8));
}

static void z62_grid_written(NikonZ72BootConfig *s,unsigned offset,uint32_t old,uint32_t value)
{
    if (!z62_grid_supported(s)) { return; }
    if ((offset==4 && !(value&1)) || (offset==0x2648 && value!=3)) {
        timer_del(s->grid_timer);
        if ((offset==4 && (old&1)) || (offset==0x2648 && old==3)) {
            memcpy(s->grid_seen_epoch,s->grid_slot_epoch,sizeof(s->grid_seen_epoch));
            s->grid_checked_seq=s->grid_source_seq;
        }
        s->grid_needs_check=false; s->grid_reason=2;
        return;
    }
    if ((offset==4 || z62_grid_config_address(offset)) && old!=value) {
        timer_del(s->grid_timer); s->grid_needs_check=true;
    }
    z62_grid_schedule(s);
}

static void z62_grid_reset(NikonZ72BootConfig *s)
{
    timer_del(s->grid_timer);
    s->grid_needs_check=false; s->grid_supplied_mask=s->grid_level_mask=0;
    s->grid_source_seq=s->grid_checked_seq=0;
    s->grid_groups=s->grid_outputs=s->grid_bytes=s->grid_rejected=s->grid_blocked=0;
    s->grid_reason=0;
    memset(s->grid_slot_epoch,0,sizeof(s->grid_slot_epoch));
    memset(s->grid_seen_epoch,0,sizeof(s->grid_seen_epoch));
}

static char *z62_grid_reason(Object *obj,Error **errp)
{
    NikonZ72BootConfig *s=NIKON_Z72_BOOT_CONFIG(obj);
    static const char *const names[]={"reset","waiting-source","disabled","configuration",
        "source-address","destination","not-ram","overlap","dma-error","numeric-input",
        "success","no-new-input"};
    return g_strdup(s->grid_reason<G_N_ELEMENTS(names)?names[s->grid_reason]:"invalid");
}

static void z62_grid_init(Object *obj)
{
    NikonZ72BootConfig *s=NIKON_Z72_BOOT_CONFIG(obj);
    s->grid_timer=timer_new_ns(QEMU_CLOCK_VIRTUAL,z62_grid_tick,s);
    qdev_init_gpio_in_named(DEVICE(obj),z62_grid_source,"z62-grid-source",6);
    object_property_add_uint64_ptr(obj,"grid-groups",&s->grid_groups,OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(obj,"grid-outputs",&s->grid_outputs,OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(obj,"grid-bytes",&s->grid_bytes,OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(obj,"grid-rejected",&s->grid_rejected,OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(obj,"grid-blocked",&s->grid_blocked,OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(obj,"grid-source-events",&s->grid_source_seq,OBJ_PROP_FLAG_READ);
    object_property_add_str(obj,"grid-reason",z62_grid_reason,NULL);
}
