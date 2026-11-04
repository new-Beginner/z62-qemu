/* SPDX-License-Identifier: GPL-2.0-or-later
 * Default-off unit20 finite C reference processing. No zero-curve fallback.
 * Configuration reads/commits alone cannot produce payloads or event96.
 */
static const unsigned group_result_offsets[]={0x370,0x374,0x378,0x478,0x578,0x37c,0x47c,0x57c};

static bool group_config_word(unsigned o)
{
    return (o<=0x180) || (o>=0x200 && o<=0x250) || (o>=0x294 && o<=0x2b8) ||
        o==0x318 || o==0x324 || o==0x33c || o==0x344 || o==0x348 || o==0x34c ||
        o==0x350 || o==0x360 || o==0x380 || o==0x450 || o==0x460 || o==0x480 ||
        o==0x550 || o==0x560 || o==0x580;
}

static void group_cancel(Z72InputConfig *s)
{
    if (s->group.generation<UINT64_MAX) s->group.generation++;
    if (s->cw.task && s->cw.task->group) s->group.cancelled++;
}

static void group_control(Z72InputConfig *s,hwaddr address,uint32_t value)
{
    Z62CWGroup *g=&s->group;
    if (!g->enabled) return;
    if ((address==0x20068100 || address==0x20068104) && (value&0x10)) {
        uint32_t profile[Z62_GROUP_WORDS]={0};bool valid=true;
        for (unsigned o=0;o<0x584;o+=4) if (group_config_word(o)) {
            valid&=s->cw.known[(0x3800+o)/4];profile[o/4]=s->registers[(0x3800+o)/4];
        }
        /* Optional opaque correction setter has no write in the observed
         * original profile. Cold-zero is the explicit C convention; an
         * actually written nonzero value still fails the numerical profile. */
        profile[0x184/4]=s->cw.known[0x3984/4]?s->registers[0x3984/4]:0;
        if (valid!=g->valid || memcmp(profile,g->profile,sizeof(profile))) {
            group_cancel(s);memcpy(g->profile,profile,sizeof(profile));g->valid=valid;
            g->cursor=profile[0x344/4];
        }
    } else if (address==0x20068000) {g->held|=value&0x20;if (value&0x20) group_cancel(s);}
    else if (address==0x20068004) g->held&=~value;
    else if (address==0x20068010) g->allowed|=value&0x20;
    else if (address==0x20068014) {g->allowed&=~value;g->running&=~value;if (value&0x20) group_cancel(s);}
    else if (address==0x20068008) g->running|=value&0x20;
    else if (address==0x2006800c) {g->running&=~value;if (value&0x20) group_cancel(s);}
    else if (address==0x20068270) g->pending&=~value;
}

typedef struct Z62GroupSpan {MemoryRegion *mr;hwaddr offset;uint64_t bytes;unsigned bank;} Z62GroupSpan;
static bool group_routes(Z72InputConfig *s,Z62CWTask *task,Z62CWGroupJob *j)
{
    Z62GroupSpan spans[48];unsigned used=0;const uint32_t *p=j->pixels.words;
    if (p[0x33c/4]>1 || p[0x344/4]>p[0x348/4] || p[0x348/4]>7 || j->cursor>p[0x348/4]) return false;
    for (unsigned bank=0;bank<2;bank++) for (unsigned family=0;family<3;family++) {
        uint64_t bytes=j->pixels.sizes[family];if (!bytes) continue;
        uint32_t pitch=p[(0x380+256*family)/4],base=p[(0x350+16*bank+256*family)/4];
        if (pitch<bytes) return false;
        for (unsigned slot=0;slot<=p[0x348/4];slot++) {
            uint64_t address=(uint64_t)base+(uint64_t)pitch*slot;hwaddr offset,span=bytes;
            if ((address&3) || !finite_memory(s,address,bytes,true)) return false;
            MemoryRegion *mr=address_space_translate(&s->raw_memory,address,&offset,&span,true,MEMTXATTRS_UNSPECIFIED);
            if (!mr || span<bytes) return false;
            for (unsigned i=0;i<used;i++) if (spans[i].bank==bank && spans[i].mr==mr &&
                offset<spans[i].offset+spans[i].bytes && spans[i].offset<offset+bytes) return false;
            spans[used++]=(Z62GroupSpan){mr,offset,bytes,bank};
            for (unsigned b=0;b<2;b++) for (unsigned n=0;n<=task->profile.buffers[7];n++) {
                uint64_t raw_address=task->profile.buffers[9+4*b+n];
                if (!raw_address) continue;
                hwaddr raw_offset,raw_span=task->packed_bytes;
                MemoryRegion *raw=address_space_translate(&s->raw_memory,raw_address,&raw_offset,&raw_span,false,MEMTXATTRS_UNSPECIFIED);
                if (raw==mr && offset<raw_offset+task->packed_bytes && raw_offset<offset+bytes) return false;
            }
        }
        if (bank==j->bank) j->address[family]=base+j->cursor*pitch;
    }
    for (unsigned family=0;family<3;family++) for (unsigned bank=0;bank<2;bank++) {
        j->results[2+bank*3+family]=p[(0x350+16*bank+256*family)/4]+
            j->cursor*p[(0x380+256*family)/4];
    }
    j->results[0]=j->bank;j->results[1]=j->cursor;
    return true;
}

static void group_admit(Z72InputConfig *s,Z62CWTask *task)
{
    Z62CWGroup *g=&s->group;
    if (!g->enabled) return;
    if (!g->valid) {g->reason=2;g->rejected++;return;}
    if ((g->held&0x20) || (g->allowed&g->running&0x20)!=0x20) {g->reason=1;return;}
    if (g->pending) {g->reason=4;g->blocked++;return;}
    if (g->generation==UINT64_MAX) {g->reason=7;return;}
    Z62CWGroupJob *j=g_new0(Z62CWGroupJob,1);
    memcpy(j->pixels.words,g->profile,sizeof(g->profile));
    j->generation=g->generation;j->cursor=g->cursor;j->bank=g->profile[0x33c/4];
    j->pixels.width=task->lease.meta.width;j->pixels.height=task->lease.meta.height;j->pixels.stride=task->lease.meta.stride;
    if (!z62_group_plan(&j->pixels,task->lease.meta.bytes)) {g->reason=3;g->rejected++;g_free(j);return;}
    if (!group_routes(s,task,j)) {g->reason=5;g->rejected++;g_free(j);return;}
    task->group=j;
}

static void group_compute_owned(Z62CWTask *task)
{
    if (task->group) task->group->success=z62_group_compute(&task->group->pixels,task->input,task->lease.meta.bytes);
}

static void group_publish(Z72InputConfig *s,Z62CWTask *task)
{
    Z62CWGroup *g=&s->group;Z62CWGroupJob *j=task->group;
    if (!j || j->generation!=g->generation) return;
    if (!j->success || g->pending || (g->held&0x20) || (g->allowed&g->running&0x20)!=0x20) {g->reason=6;g->rejected++;return;}
    if (!group_routes(s,task,j)) {g->reason=5;g->rejected++;return;}
    uint8_t merged[Z62_GROUP_MAX_DATA];unsigned offset=0;
    for (unsigned family=0;family<3;family++) {
        unsigned bytes=j->pixels.sizes[family];if (!bytes) continue;
        if (address_space_read(&s->raw_memory,j->address[family],MEMTXATTRS_UNSPECIFIED,merged+offset,bytes)!=MEMTX_OK) {
            g->reason=6;g->rejected++;return;
        }
        unsigned count=family==2?j->pixels.cells:1,stride=family==0?40:family==1?24:32;
        for (unsigned n=0;n<count;n++) {
            uint8_t *to=merged+offset+n*stride;const uint8_t *from=j->pixels.data+offset+n*stride;
            memcpy(to,from,20);
            if (family!=1) {memcpy(to+20,from+20,2);memcpy(to+24,from+24,6);if (!family) memcpy(to+32,from+32,6);}
        }
        offset+=bytes;
    }
    offset=0;
    for (unsigned family=0;family<3;family++) {
        unsigned bytes=j->pixels.sizes[family];if (!bytes) continue;
        if (address_space_write(&s->raw_memory,j->address[family],MEMTXATTRS_UNSPECIFIED,merged+offset,bytes)!=MEMTX_OK) {
            g->reason=6;g->rejected++;return;
        }
        offset+=bytes;
    }
    for (unsigned i=0;i<8;i++) s->registers[(0x3800+group_result_offsets[i])/4]=j->results[i];
    g->completed++;g->bytes+=offset;g->reason=8;g->pending=1;g->meta=task->lease.meta;
    g->cursor=(j->cursor+1)%(j->pixels.words[0x348/4]+1);
    memcpy(g->last_address,j->address,sizeof(j->address));memcpy(g->last_size,j->pixels.sizes,sizeof(j->pixels.sizes));
    g->last_cursor=j->cursor;g->last_bank=j->bank;
    qemu_irq_pulse(s->cw.complete[3]);
}

static char *group_status(Object *obj,Error **errp)
{
    Z62CWGroup *g=&Z72_INPUT_CONFIG(obj)->group;
    return g_strdup_printf("{\"enabled\":%s,\"committed\":%s,\"reason\":%u,\"pending\":%u,"
        "\"generation\":%" PRIu64 ",\"completed\":%" PRIu64 ",\"rejected\":%" PRIu64 ","
        "\"cancelled\":%" PRIu64 ",\"blocked\":%" PRIu64 ",\"bytes\":%" PRIu64 ","
        "\"epoch\":%" PRIu64 ",\"publication\":%" PRIu64 ",\"frame\":%" PRIu64 ",\"time_ns\":%" PRIu64 ","
        "\"cursor\":%u,\"bank\":%u,\"addresses\":[%u,%u,%u],\"sizes\":[%u,%u,%u],"
        "\"math\":\"C-reference-LUT65-horizontal-FIR\",\"physical_AF_equivalence\":false}",
        g->enabled?"true":"false",g->valid?"true":"false",g->reason,g->pending,g->generation,
        g->completed,g->rejected,g->cancelled,g->blocked,g->bytes,g->meta.epoch,g->meta.publication,
        g->meta.frame,g->meta.time_ns,g->last_cursor,g->last_bank,g->last_address[0],g->last_address[1],
        g->last_address[2],g->last_size[0],g->last_size[1],g->last_size[2]);
}

static void group_reset(Z72InputConfig *s)
{
    bool enabled=s->group.enabled;uint64_t generation=s->group.generation;
    memset(&s->group,0,sizeof(s->group));s->group.enabled=enabled;s->group.generation=generation;
}
