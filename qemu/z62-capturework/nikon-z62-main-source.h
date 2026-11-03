/* SPDX-License-Identifier: GPL-2.0-or-later
 * Level-C MAIN mailbox and read lease. Single serialized owner (future BQL).
 * No guest registers, DMA, timer or IRQ; release is ownership, not completion.
 * External memory belongs to this model and must not be modified while leased.
 */
#ifndef NIKON_Z62_MAIN_SOURCE_H
#define NIKON_Z62_MAIN_SOURCE_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

#define Z62_MAIN_HEADER 96u
#define Z62_MAIN_MAX_BYTES (UINT64_C(64)*1024*1024)

typedef enum Z62MainResult {
    Z62_MAIN_OK, Z62_MAIN_PACKET, Z62_MAIN_GEOMETRY, Z62_MAIN_CRC,
    Z62_MAIN_SEQUENCE, Z62_MAIN_BUSY, Z62_MAIN_STATE, Z62_MAIN_STALE,
    Z62_MAIN_CAPACITY
} Z62MainResult;

typedef struct Z62MainMetadata {
    uint32_t width, height, stride, bytes, black, white, crc;
    uint64_t epoch, publication, frame, time_ns;
} Z62MainMetadata;

typedef struct Z62MainSource {
    uint8_t *pixels;
    size_t capacity;
    Z62MainMetadata meta;
    uint64_t serial;
    bool valid, running, leased;
} Z62MainSource;

typedef struct Z62MainLease {
    const uint8_t *pixels;
    Z62MainMetadata meta;
    uint64_t serial;
} Z62MainLease;

static inline uint32_t z62_main_u32(const uint8_t *p)
{ return (uint32_t)p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24; }
static inline uint64_t z62_main_u64(const uint8_t *p)
{ return z62_main_u32(p)|(uint64_t)z62_main_u32(p+4)<<32; }

static inline uint32_t z62_main_crc32(const uint8_t *p, size_t size)
{
    uint32_t crc=UINT32_MAX;
    for (size_t i=0;i<size;i++) {
        crc^=p[i];
        for (unsigned b=0;b<8;b++) crc=(crc>>1)^((0u-(crc&1u))&UINT32_C(0xedb88320));
    }
    return ~crc;
}

static inline Z62MainResult z62_main_parse(const uint8_t *packet, size_t size,
                                         Z62MainMetadata *metadata)
{
    Z62MainMetadata m={0};
    if (!packet || !metadata || size<Z62_MAIN_HEADER || size>Z62_MAIN_HEADER+Z62_MAIN_MAX_BYTES ||
        memcmp(packet,"Z62M",4) || z62_main_u32(packet+4)!=1 ||
        z62_main_u32(packet+8)!=Z62_MAIN_HEADER || z62_main_u32(packet+12)!=1 ||
        z62_main_u32(packet+64)!=1 || z62_main_u32(packet+68)!=1 ||
        z62_main_u32(packet+80) || z62_main_u32(packet+92)) return Z62_MAIN_PACKET;
    m.width=z62_main_u32(packet+16); m.height=z62_main_u32(packet+20);
    m.stride=z62_main_u32(packet+24); m.bytes=z62_main_u32(packet+28);
    m.epoch=z62_main_u64(packet+32); m.publication=z62_main_u64(packet+40);
    m.frame=z62_main_u64(packet+48); m.time_ns=z62_main_u64(packet+56);
    m.black=z62_main_u32(packet+72); m.white=z62_main_u32(packet+76); m.crc=z62_main_u32(packet+84);
    uint64_t bytes=(uint64_t)m.stride*m.height;
    if (!m.width || !m.height || m.width>4096 || m.height>4096 ||
        ((m.width|m.height|m.stride)&1u) || (uint64_t)m.width*m.height>UINT64_C(4)*1024*1024 ||
        m.stride<2*m.width || bytes>Z62_MAIN_MAX_BYTES || bytes!=m.bytes ||
        bytes+Z62_MAIN_HEADER!=size || m.black>=m.white || m.white>65535) return Z62_MAIN_GEOMETRY;
    if (!m.publication || m.publication>INT64_MAX || m.time_ns>INT64_MAX ||
        m.frame!=(m.time_ns/1000000000)*30+(m.time_ns%1000000000)*30/1000000000) return Z62_MAIN_SEQUENCE;
    if (z62_main_crc32(packet,88)!=z62_main_u32(packet+88) ||
        z62_main_crc32(packet+Z62_MAIN_HEADER,m.bytes)!=m.crc) return Z62_MAIN_CRC;
    for (uint32_t y=0;y<m.height;y++) for (uint32_t x=2*m.width;x<m.stride;x++)
        if (packet[Z62_MAIN_HEADER+(size_t)y*m.stride+x]) return Z62_MAIN_PACKET;
    *metadata=m;
    return Z62_MAIN_OK;
}

static inline bool z62_main_source_init(Z62MainSource *s, uint8_t *memory, size_t capacity)
{
    if (!s || !memory || !capacity || capacity>Z62_MAIN_MAX_BYTES) return false;
    *s=(Z62MainSource){.pixels=memory,.capacity=capacity,.serial=1};
    return true;
}

static inline Z62MainResult z62_main_source_publish(Z62MainSource *s, const uint8_t *packet, size_t size)
{
    Z62MainMetadata meta;
    if (!s || !s->pixels) return Z62_MAIN_STATE;
    if (s->leased) return Z62_MAIN_BUSY;
    Z62MainResult result=z62_main_parse(packet,size,&meta);
    if (result!=Z62_MAIN_OK) return result;
    if (meta.bytes>s->capacity) return Z62_MAIN_CAPACITY;
    if (s->valid && (meta.epoch!=s->meta.epoch || meta.publication<=s->meta.publication ||
                    meta.time_ns<s->meta.time_ns)) return Z62_MAIN_SEQUENCE;
    memmove(s->pixels,packet+Z62_MAIN_HEADER,meta.bytes);
    s->meta=meta; s->valid=true;
    return Z62_MAIN_OK;
}

static inline Z62MainResult z62_main_source_start(Z62MainSource *s)
{
    if (!s || !s->valid || s->serial==UINT64_MAX) return Z62_MAIN_STATE;
    s->running=true;
    return Z62_MAIN_OK;
}

static inline Z62MainResult z62_main_source_begin(Z62MainSource *s, Z62MainLease *lease)
{
    if (!s || !lease || !s->running || !s->valid || s->serial==UINT64_MAX) return Z62_MAIN_STATE;
    if (s->leased) return Z62_MAIN_BUSY;
    s->serial++; s->leased=true;
    *lease=(Z62MainLease){.pixels=s->pixels,.meta=s->meta,.serial=s->serial};
    return Z62_MAIN_OK;
}

static inline Z62MainResult z62_main_source_release(Z62MainSource *s, const Z62MainLease *lease)
{
    if (!s || !lease || !s->leased || lease->serial!=s->serial || lease->pixels!=s->pixels ||
        lease->meta.epoch!=s->meta.epoch || lease->meta.publication!=s->meta.publication) return Z62_MAIN_STALE;
    s->leased=false;
    return Z62_MAIN_OK;
}

static inline void z62_main_source_cancel(Z62MainSource *s)
{
    if (!s) return;
    s->leased=false;
    if (s->serial<UINT64_MAX) s->serial++;
    else s->running=false;
}

static inline void z62_main_source_stop(Z62MainSource *s)
{
    if (!s) return;
    z62_main_source_cancel(s); s->running=false;
}

/* Reset preserves the external publication/epoch, matching the scene model.
 * It invalidates outstanding work and requires a new explicit start. */
static inline void z62_main_source_reset(Z62MainSource *s)
{ z62_main_source_stop(s); }
#endif
