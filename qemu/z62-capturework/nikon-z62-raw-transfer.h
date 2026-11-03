/* SPDX-License-Identifier: GPL-2.0-or-later
 * Explicit C-model transfer snapshot. No MMIO, guest writes, DMA or IRQ.
 * A lookup8 code identifies [index*256,index*256+255], not the original low
 * byte. Linear16 reconstruction uses that interval's upper midpoint.
 */
#ifndef NIKON_Z62_RAW_TRANSFER_H
#define NIKON_Z62_RAW_TRANSFER_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

#define Z62_TRANSFER_BYTES 532u
#define Z62_TRANSFER_MAX_BYTES (UINT64_C(64)*1024*1024)
typedef enum Z62TransferResult {
    Z62_TRANSFER_OK, Z62_TRANSFER_CONFIG, Z62_TRANSFER_CODE,
    Z62_TRANSFER_GEOMETRY, Z62_TRANSFER_SPAN, Z62_TRANSFER_OVERLAP
} Z62TransferResult;

typedef struct Z62RawTransfer {
    uint32_t bits, codec;
    uint16_t lookup[256];
} Z62RawTransfer;

typedef struct Z62RawInterval {
    uint32_t lower, upper, representative, quantum;
} Z62RawInterval;

static inline bool z62_transfer_valid(const Z62RawTransfer *t)
{
    if (!t || (t->bits!=12 && t->bits!=14 && t->bits!=16) || t->codec>1) return false;
    for (unsigned i=0;i<256;i++) {
        if (!t->codec) { if (t->lookup[i]) return false; }
        else if ((uint32_t)t->lookup[i]>=(UINT32_C(1)<<t->bits) ||
                 (i && t->lookup[i]<=t->lookup[i-1])) return false;
    }
    return true;
}

static inline Z62TransferResult z62_transfer_snapshot(Z62RawTransfer *output,
    uint32_t bits, uint32_t codec, const uint16_t *lookup)
{
    if (!output || (codec && !lookup)) return Z62_TRANSFER_CONFIG;
    Z62RawTransfer t={.bits=bits,.codec=codec};
    if (codec==1) memcpy(t.lookup,lookup,sizeof(t.lookup));
    if (!z62_transfer_valid(&t)) return Z62_TRANSFER_CONFIG;
    *output=t;
    return Z62_TRANSFER_OK;
}

static inline uint32_t z62_transfer_u32(const uint8_t *p)
{ return (uint32_t)p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24; }
static inline uint32_t z62_transfer_crc(const uint8_t *p,size_t size)
{
    uint32_t crc=UINT32_MAX;
    for (size_t i=0;i<size;i++) {
        crc^=p[i];
        for (unsigned bit=0;bit<8;bit++) crc=(crc>>1)^((0u-(crc&1u))&UINT32_C(0xedb88320));
    }
    return ~crc;
}

static inline Z62TransferResult z62_transfer_load(Z62RawTransfer *output,const uint8_t *blob,size_t size)
{
    if (!output || !blob || size!=Z62_TRANSFER_BYTES || memcmp(blob,"Z62T",4) ||
        z62_transfer_u32(blob+4)!=1 || z62_transfer_crc(blob,528)!=z62_transfer_u32(blob+528)) return Z62_TRANSFER_CONFIG;
    Z62RawTransfer t={.bits=z62_transfer_u32(blob+8),.codec=z62_transfer_u32(blob+12)};
    for (unsigned i=0;i<256;i++) t.lookup[i]=(uint16_t)((unsigned)blob[16+2*i]|(unsigned)blob[17+2*i]<<8);
    if (!z62_transfer_valid(&t)) return Z62_TRANSFER_CONFIG;
    *output=t;
    return Z62_TRANSFER_OK;
}

/* Internal: caller has already validated the frozen descriptor. */
static inline bool z62_transfer_interval_known(const Z62RawTransfer *t,uint32_t code,Z62RawInterval *value)
{
    uint32_t quantum,index;
    if (code>=(UINT32_C(1)<<t->bits)) return false;
    if (t->codec) {
        unsigned lo=0,hi=256;
        while (lo<hi) {
            unsigned middle=lo+(hi-lo)/2;
            if (t->lookup[middle]<code) lo=middle+1; else hi=middle;
        }
        if (lo==256 || t->lookup[lo]!=code) return false;
        quantum=256; index=lo;
    } else { quantum=UINT32_C(1)<<(16-t->bits); index=code; }
    uint32_t lower=index*quantum;
    *value=(Z62RawInterval){.lower=lower,.upper=lower+quantum-1,
        .representative=lower+quantum/2,.quantum=quantum};
    return true;
}

static inline Z62TransferResult z62_transfer_interval(const Z62RawTransfer *t,uint32_t code,Z62RawInterval *value)
{
    if (!value || !z62_transfer_valid(t)) return Z62_TRANSFER_CONFIG;
    return z62_transfer_interval_known(t,code,value)?Z62_TRANSFER_OK:Z62_TRANSFER_CODE;
}

static inline uint32_t z62_transfer_read_code(const uint8_t *row,uint32_t sample,uint32_t bits)
{
    uint32_t result=0,start=sample*bits;
    for (unsigned bit=0;bit<bits;bit++) result|=((uint32_t)(row[(start+bit)/8]>>((start+bit)%8))&1u)<<bit;
    return result;
}

static inline Z62TransferResult z62_transfer_unpack(const Z62RawTransfer *transfer,
    const uint8_t *source,size_t source_size,uint32_t width,uint32_t height,uint32_t source_stride,
    uint8_t *destination,size_t destination_size,uint32_t destination_stride)
{
    if (!transfer || !source || !destination) return Z62_TRANSFER_CONFIG;
    const Z62RawTransfer t=*transfer; /* No live register/LUT pointer during work. */
    if (!z62_transfer_valid(&t)) return Z62_TRANSFER_CONFIG;
    uint64_t row_bits=(uint64_t)width*t.bits;
    if (!width || !height || width>4096 || height>4096 || (uint64_t)width*height>UINT64_C(4)*1024*1024 ||
        (row_bits&7u) || source_stride<row_bits/8 || destination_stride<2*width) return Z62_TRANSFER_GEOMETRY;
    uint64_t src_bytes=(uint64_t)source_stride*height,dst_bytes=(uint64_t)destination_stride*height;
    if (src_bytes>Z62_TRANSFER_MAX_BYTES || dst_bytes>Z62_TRANSFER_MAX_BYTES ||
        src_bytes>source_size || dst_bytes>destination_size || src_bytes>SIZE_MAX || dst_bytes>SIZE_MAX) return Z62_TRANSFER_SPAN;
    uintptr_t src=(uintptr_t)source,dst=(uintptr_t)destination;
    if (src_bytes>UINTPTR_MAX-src || dst_bytes>UINTPTR_MAX-dst ||
        (src<dst+dst_bytes && dst<src+src_bytes)) return Z62_TRANSFER_OVERLAP;
    /* Every encoded sample must be understood before the first output write. */
    for (uint32_t y=0;y<height;y++) for (uint32_t x=0;x<width;x++) {
        Z62RawInterval value;
        if (!z62_transfer_interval_known(&t,z62_transfer_read_code(source+(size_t)y*source_stride,x,t.bits),&value))
            return Z62_TRANSFER_CODE;
    }
    for (uint32_t y=0;y<height;y++) for (uint32_t x=0;x<width;x++) {
        Z62RawInterval value;
        if (!z62_transfer_interval_known(&t,z62_transfer_read_code(source+(size_t)y*source_stride,x,t.bits),&value))
            return Z62_TRANSFER_CODE; /* serialized immutable input required */
        uint8_t *p=destination+(size_t)y*destination_stride+2*x;
        p[0]=(uint8_t)value.representative; p[1]=(uint8_t)(value.representative>>8);
    }
    return Z62_TRANSFER_OK;
}
#endif
