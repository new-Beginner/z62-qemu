/* SPDX-License-Identifier: GPL-2.0-or-later
 * Explicit finite C reference operator, NOT Nikon filter/AF arithmetic.
 * Wire classification/reference: nightglasses/z7ii-qemu capturegroup.c,
 * commit 0e53ea5a6d4f3fc635d63c195a92e943370ac5e9, GPL-2.0-or-later.
 * Z62 configuration/control/consumer instructions are audited independently.
 * No MMIO, DMA, IRQ, guest flags or synthetic fallback parameters here.
 */
#ifndef NIKON_Z62_GROUP_PIXELS_H
#define NIKON_Z62_GROUP_PIXELS_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

#define Z62_GROUP_WORDS (0x584u/4)
#define Z62_GROUP_MAX_DATA (40u+24u+81u*32u)
typedef struct Z62GroupRectangle { uint32_t x,y,w,h; } Z62GroupRectangle;
typedef struct Z62GroupPixels {
    uint32_t words[Z62_GROUP_WORDS], width,height,stride;
    Z62GroupRectangle roi[2];
    uint32_t domain_w,domain_h,columns,rows,cells,families,sizes[3];
    int coefficients[3][8]; unsigned magnitude[3];
    uint8_t data[Z62_GROUP_MAX_DATA];
} Z62GroupPixels;

static inline uint32_t z62_group_word(const Z62GroupPixels *p,unsigned offset)
{ return p->words[offset/4]; }
static inline bool z62_group_rectangle(Z62GroupRectangle r,uint32_t w,uint32_t h)
{ return r.w && r.h && r.x<w && r.y<h && r.w<=w-r.x && r.h<=h-r.y; }
static inline void z62_group_put32(uint8_t *p,uint64_t v)
{ p[0]=(uint8_t)v;p[1]=(uint8_t)(v>>8);p[2]=(uint8_t)(v>>16);p[3]=(uint8_t)(v>>24); }
static inline void z62_group_put16(uint8_t *p,uint32_t v)
{ p[0]=(uint8_t)v;p[1]=(uint8_t)(v>>8); }
static inline uint64_t z62_group_min(uint64_t a,uint64_t b) { return a<b?a:b; }

static inline bool z62_group_plan(Z62GroupPixels *p,size_t input_bytes)
{
    if (!p || !p->width || !p->height || p->width>4096 || p->height>4096 ||
        (uint64_t)p->width*p->height>UINT64_C(4)*1024*1024 || p->stride<2*p->width ||
        (p->stride&1) || (uint64_t)p->stride*p->height>input_bytes ||
        (uint64_t)p->stride*p->height>UINT64_C(64)*1024*1024) return false;
    static const unsigned zero[]={0x18,0x1c,0x184,0x200,0x204,0x210,0x214,0x218,
        0x21c,0x220,0x224,0x228,0x294,0x298,0x29c,0x2a0,0x2a4,0x2a8,0x2ac,0x2b0,0x2b4,0x2b8};
    for (unsigned i=0;i<sizeof(zero)/sizeof(zero[0]);i++) if (z62_group_word(p,zero[i])) return false;
    p->domain_w=z62_group_word(p,0x208);p->domain_h=z62_group_word(p,0x20c);
    p->families=z62_group_word(p,0x22c);
    if (!p->domain_w || !p->domain_h || p->domain_w>16384 || p->domain_h>16384 ||
        !p->families || p->families>3) return false;
    if (p->families&1) {
        if (z62_group_word(p,0x230)!=1) return false;
        for (unsigned i=0;i<2;i++) {
            const uint32_t *r=&p->words[(0x234+16*i)/4];
            p->roi[i]=(Z62GroupRectangle){r[0],r[1],r[2],r[3]};
            if (!z62_group_rectangle(p->roi[i],p->domain_w,p->domain_h)) return false;
        }
    }
    p->columns=p->rows=p->cells=0;
    if (p->families&2) {
        unsigned a=z62_group_word(p,0),b=z62_group_word(p,4);
        unsigned sx=z62_group_word(p,0x10),sy=z62_group_word(p,0x14);
        if (a>8 || b>8 || !sx || !sy || sx>16384 || sy>16384 ||
            z62_group_word(p,8)<sx/2 || z62_group_word(p,12)<sy/2 ||
            (uint64_t)z62_group_word(p,8)+a*sx+(sx+1)/2>p->domain_w ||
            (uint64_t)z62_group_word(p,12)+b*sy+(sy+1)/2>p->domain_h) return false;
        p->columns=a+1;p->rows=b+1;p->cells=p->columns*p->rows;
    }
    for (unsigned i=0;i<65;i++) {
        uint32_t value=z62_group_word(p,0x80+4*i);
        if (value>65535 || (i && value<z62_group_word(p,0x7c+4*i))) return false;
    }
    if (z62_group_word(p,0x80)==z62_group_word(p,0x180)) return false;
    for (unsigned f=0;f<3;f++) {
        p->magnitude[f]=0;
        for (unsigned tap=0;tap<8;tap++) {
            uint32_t value=z62_group_word(p,0x20+f*32+tap*4),bits=tap?7:8;
            if (value>=(1u<<bits)) return false;
            int c=(value&(1u<<(bits-1)))?(int)value-(int)(1u<<bits):(int)value;
            p->coefficients[f][tap]=c;p->magnitude[f]+=(unsigned)(c<0?-c:c);
        }
        if (!p->magnitude[f]) return false;
    }
    p->sizes[0]=(p->families&1)?40:0;p->sizes[1]=(p->families&1)?24:0;
    p->sizes[2]=(p->families&2)?p->cells*32:0;
    return true;
}

static inline uint32_t z62_group_sample(const Z62GroupPixels *p,const uint8_t *raw,unsigned x,unsigned y)
{
    const uint8_t *v=raw+(size_t)y*p->stride+2*x;
    unsigned value=(unsigned)v[0]|(unsigned)v[1]<<8,index=value>>10,fraction=value&1023;
    uint32_t a=z62_group_word(p,0x80+index*4),b=z62_group_word(p,0x84+index*4);
    return ((a*(1024-fraction)+b*fraction)/1024)>>4;
}

static inline void z62_group_record(const Z62GroupPixels *p,const uint8_t *raw,
    Z62GroupRectangle r,unsigned kind,uint8_t *out)
{
    unsigned x0=(uint64_t)r.x*p->width/p->domain_w,y0=(uint64_t)r.y*p->height/p->domain_h;
    unsigned x1=((uint64_t)(r.x+r.w)*p->width+p->domain_w-1)/p->domain_w;
    unsigned y1=((uint64_t)(r.y+r.h)*p->height+p->domain_h-1)/p->domain_h;
    uint64_t sums[5]={0},count=(uint64_t)r.w*r.h,samples=(uint64_t)(x1-x0)*(y1-y0);
    for (unsigned y=y0;y<y1;y++) for (unsigned x=x0;x<x1;x++) {
        unsigned value=z62_group_sample(p,raw,x,y);sums[0]+=value;sums[1]+=(uint64_t)value*value;
        for (unsigned f=0;f<3;f++) {
            int response=0;
            for (unsigned tap=0;tap<8;tap++) if (p->coefficients[f][tap]) {
                int sx=(int)x+(int)tap-3;if (sx<0) sx=0;if (sx>=(int)p->width) sx=(int)p->width-1;
                response+=p->coefficients[f][tap]*(int)z62_group_sample(p,raw,(unsigned)sx,y);
            }
            sums[2+f]+=(unsigned)(response<0?-response:response)/p->magnitude[f];
        }
    }
    uint64_t largest=0;
    for (unsigned i=0;i<5;i++) {
        sums[i]=sums[i]/samples*count+(sums[i]%samples)*count/samples;
        if (i>=2 && sums[i]/count>largest) largest=sums[i]/count;
    }
    if (kind==1) {
        z62_group_put32(out,z62_group_min(sums[0],UINT32_MAX));z62_group_put32(out+4,count);
        for (unsigned i=0;i<3;i++) z62_group_put32(out+8+4*i,z62_group_min(sums[2+i],UINT32_MAX));
        return;
    }
    uint64_t sum23=z62_group_min(sums[0],0x7fffff),energy29=z62_group_min(sums[1],0x1fffffff);
    z62_group_put32(out,z62_group_min(largest,0xfff)|(sum23<<12));
    z62_group_put32(out+4,(sum23>>20)|(energy29<<3));
    z62_group_put32(out+8,z62_group_min(sums[0],UINT32_MAX));z62_group_put32(out+12,count);
    z62_group_put32(out+16,z62_group_min(sums[2],UINT32_MAX));z62_group_put16(out+20,(uint32_t)(sums[0]/count));
    z62_group_put32(out+24,z62_group_min(sums[3],UINT32_MAX));z62_group_put16(out+28,r.x+r.w/2);
    if (!kind) {z62_group_put32(out+32,z62_group_min(sums[4],UINT32_MAX));z62_group_put16(out+36,r.y+r.h/2);}
}

static inline bool z62_group_compute(Z62GroupPixels *p,const uint8_t *raw,size_t bytes)
{
    if (!raw || !z62_group_plan(p,bytes)) return false;
    unsigned offset=0;
    for (unsigned family=0;family<3;family++) {
        if (!p->sizes[family]) continue;
        if (family<2) z62_group_record(p,raw,p->roi[family],family,p->data+offset);
        else {
            unsigned sx=z62_group_word(p,0x10),sy=z62_group_word(p,0x14);
            for (unsigned cell=0;cell<p->cells;cell++) {
                Z62GroupRectangle r={z62_group_word(p,8)+(cell%p->columns)*sx-sx/2,
                    z62_group_word(p,12)+(cell/p->columns)*sy-sy/2,sx,sy};
                z62_group_record(p,raw,r,2,p->data+offset+cell*32);
            }
        }
        offset+=p->sizes[family];
    }
    return true;
}
#endif
