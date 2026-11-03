/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../../qemu/z62-video-source/nikon-z62-video-source-pixels.h"

#define CHECK(value) do { if (!(value)) { fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#value); return 1; } } while (0)

static unsigned unpack(const uint8_t *p, unsigned x)
{
    p += x/2*3;
    return (x&1) ? (p[1]>>4) | (unsigned)p[2]<<4 : p[0] | (unsigned)(p[1]&15)<<8;
}

static void pack(uint8_t *p, unsigned a, unsigned b)
{
    p[0]=a; p[1]=(a>>8) | ((b&15)<<4); p[2]=b>>4;
}

static unsigned pattern(unsigned x, unsigned y)
{
    return (x*7+y*11+0x123)&4095;
}

int main(void)
{
    const uint8_t source[32]={
        0x01,0x40,0x23,0x67,0xa5,0x89,0xd3,0xd3,
        0xbc,0xfa,0xde,0x23,0x61,0x45,0xd3,0xd3,
        0x89,0xc7,0xab,0xef,0x2d,0x01,0xd3,0xd3,
        0x45,0x83,0x67,0xab,0xe9,0xcd,0xd3,0xd3};
    uint8_t out[80], before[80];
    memset(out,0xa5,sizeof(out));
    CHECK(z62_video_raw_view(source,30,4,4,8,out+8,21,6,2,12,0,2));
    const uint8_t expected[2][9]={
        {0x89,0xc7,0xab,0xef,0x2d,0x01,0xef,0x2d,0x01},
        {0x45,0x83,0x67,0xab,0xe9,0xcd,0xab,0xe9,0xcd}};
    for(unsigned y=0;y<2;y++) {
        CHECK(!memcmp(out+8+y*12,expected[y],9));
        for(unsigned x=9;x<12;x++) CHECK(out[8+y*12+x]==0xa5);
    }
    for(unsigned i=0;i<8;i++) CHECK(out[i]==0xa5);
    for(unsigned i=32;i<sizeof(out);i++) CHECK(out[i]==0xa5);

    memset(out,0xa5,sizeof(out));
    CHECK(z62_video_raw_view(source,sizeof(source),4,4,8,out+8,48,4,6,8,-2,-2));
    const uint8_t padded[6][6]={
        {0x01,0x40,0x23,0x01,0x40,0x23}, {0xbc,0xfa,0xde,0xbc,0xfa,0xde},
        {0x01,0x40,0x23,0x01,0x40,0x23}, {0xbc,0xfa,0xde,0xbc,0xfa,0xde},
        {0x89,0xc7,0xab,0x89,0xc7,0xab}, {0x45,0x83,0x67,0x45,0x83,0x67}};
    for(unsigned y=0;y<6;y++) {
        CHECK(!memcmp(out+8+y*8,padded[y],6));
        CHECK(out[8+y*8+6]==0xa5 && out[8+y*8+7]==0xa5);
    }
    /* Bottom/right replication must retain alternating CFA row colors too. */
    memset(out,0xa5,sizeof(out));
    CHECK(z62_video_raw_view(source,sizeof(source),4,4,8,out+8,32,4,4,8,2,2));
    const uint8_t bottom[2][6]={
        {0xef,0x2d,0x01,0xef,0x2d,0x01}, {0xab,0xe9,0xcd,0xab,0xe9,0xcd}};
    for(unsigned y=0;y<4;y++) {
        CHECK(!memcmp(out+8+y*8,bottom[y%2],6));
        CHECK(out[8+y*8+6]==0xa5 && out[8+y*8+7]==0xa5);
    }
    memset(out,0xa5,sizeof(out));
    CHECK(z62_video_raw_view(source,sizeof(source),4,4,8,out,40,4,4,10,0,0));
    for(unsigned y=0;y<4;y++) CHECK(!memcmp(out+y*10,source+y*8,6));
    memset(out,0xa5,sizeof(out)); memcpy(before,out,sizeof(out));
    CHECK(!z62_video_raw_view(source,29,4,4,8,out,24,6,2,12,0,2));
    CHECK(!z62_video_raw_view(source,32,4,4,8,out,20,6,2,12,0,2));
    CHECK(!z62_video_raw_view(source,32,4,4,5,out,24,6,2,12,0,2));
    CHECK(!z62_video_raw_view(source,32,4,4,8,out,24,6,2,8,0,2));
    CHECK(!z62_video_raw_view(source,32,4,4,8,out,24,5,2,12,0,2));
    CHECK(!z62_video_raw_view(source,32,4,4,8,out,24,6,2,12,1,2));
    CHECK(!z62_video_raw_view(source,32,4,4,8,out,24,6,2,12,0,1));
    CHECK(!z62_video_raw_view(source,32,4,4,8,out,24,6,2,12,0,4097));
    CHECK(!z62_video_raw_view(NULL,32,4,4,8,out,24,6,2,12,0,2));
    CHECK(!z62_video_raw_view((const uint8_t *)(UINTPTR_MAX-3),32,4,4,8,out,24,6,2,12,0,2));
    CHECK(!memcmp(out,before,sizeof(out)));
    CHECK(!z62_video_raw_view(out,sizeof(out),4,4,8,out+4,24,6,2,12,0,2));
    CHECK(!memcmp(out,before,sizeof(out)));

    const size_t input_size=2272*1006, output_size=2288*854;
    uint8_t *input=malloc(input_size), *saved=malloc(input_size), *target=malloc(output_size+32);
    CHECK(input && saved && target);
    memset(input,0xd3,input_size); memset(target,0xa5,output_size+32);
    for(unsigned y=0;y<1006;y++) for(unsigned x=0;x<1514;x+=2)
        pack(input+(size_t)y*2272+x/2*3,pattern(x,y),pattern(x+1,y));
    memcpy(saved,input,input_size);
    /* Caller-chosen C example, not a Nikon ROI claim: keep CFA phase, crop
     * 76 rows at top/bottom, append one same-color cell at the right. */
    CHECK(z62_video_raw_view(input,input_size,1514,1006,2272,target+16,output_size,1516,854,2288,0,76));
    for(unsigned y=0;y<854;y++) {
        for(unsigned x=0;x<1516;x++) {
            unsigned sx=x<1514 ? x : 1512+(x&1);
            CHECK(unpack(target+16+(size_t)y*2288,x)==pattern(sx,y+76));
        }
        for(unsigned x=2274;x<2288;x++) CHECK(target[16+(size_t)y*2288+x]==0xa5);
    }
    for(unsigned x=0;x<16;x++) CHECK(target[x]==0xa5 && target[16+output_size+x]==0xa5);
    CHECK(!memcmp(input,saved,input_size));
    free(input); free(saved); free(target);
    puts("PASS: literal crop/pad vectors, CFA parity, independent strides, rejects-before-write, real 1516x854 view; no QEMU/IRQ");
    return 0;
}
