/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef NIKON_Z62_VIDEO_PROFILE_H
#define NIKON_Z62_VIDEO_PROFILE_H
#include <string.h>
#include "nikon-z62-preview-results-profile.h"
static inline uint32_t z62_video_result_mask(unsigned i,uint32_t w,uint32_t h,const uint32_t *r,const uint8_t *p)
{
    static const struct { unsigned width,height,rows,old_height,old_rows; } units[]={
        {1920,1080,1088,1080,1108}, {1024,576,582,682,700}, {1024,576,582,680,698}};
    if(i>=3 || !r || !p || w!=units[i].width || h!=units[i].height ||
       z62_result_word(p,0x30)!=(units[i].rows-1)<<16) return 0;
    uint8_t copy[160];memcpy(copy,p,sizeof(copy));
    uint32_t rows=(units[i].old_rows-1)<<16;
    for(unsigned j=0;j<4;j++) copy[0x30+j]=(uint8_t)(rows>>(j*8));
    return z62_preview_result_mask(i,w,units[i].old_height,r,copy);
}

/* Fixed numerical tuple captured from Z62 r57. Controls, request ownership,
 * DMA addresses and active layouts are checked separately. Unsupported opaque
 * values never become an identity-calibration fallback. */
static inline bool z62_video_paired_profile(const uint32_t *r)
{
    static const struct {unsigned offset;uint32_t value;} fields[]={
        {0x48,0x05ec0356},{0x88,0},{0x8c,3},{0x94,0},{0x9c,853},{0xa8,4},
        {0x10c,0},{0x138,0},{0x13c,0},{0x140,0},{0x300,0},{0x30c,2288},
        {0x3d8,2},{0x400,0x0004034e},{0x404,1},{0x408,1},{0x40c,0x05e40004},
        {0x410,1},{0x414,0},{0x420,1},{0x424,0},{0x428,1},{0x42c,3},
        {0x470,1520},{0x4c8,1520}
    };
    static const uint32_t opaque[]={
        UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),
        UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),
        UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),
        UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),
        UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0xe000e),UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x17771777),UINT32_C(0x17771777),
        UINT32_C(0x17771777),UINT32_C(0x320032),UINT32_C(0x320032),UINT32_C(0x320032),UINT32_C(0x10001),UINT32_C(0x10001),UINT32_C(0x10001),UINT32_C(0x320032),
        UINT32_C(0x320032),UINT32_C(0x320032),UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x100010),UINT32_C(0x100010),UINT32_C(0x100010),
        UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x3fff3fff),UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),
        UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x1),UINT32_C(0x800080),UINT32_C(0x800080),UINT32_C(0x800080),UINT32_C(0x800080),UINT32_C(0x0),
        UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x1),UINT32_C(0x1040),UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),
        UINT32_C(0x0),UINT32_C(0x20),UINT32_C(0x70007),UINT32_C(0x30001),UINT32_C(0x0),UINT32_C(0x70007),UINT32_C(0x30001),UINT32_C(0x0),
        UINT32_C(0x13),UINT32_C(0x70009),UINT32_C(0x5020404),UINT32_C(0x1c1c1c1c),UINT32_C(0x0),UINT32_C(0x3020001),UINT32_C(0x0),UINT32_C(0x100),
        UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),
        UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),
        UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),
        UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),
        UINT32_C(0x100),UINT32_C(0x0),UINT32_C(0x35a0200),UINT32_C(0x20002c5),UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x12c012c),UINT32_C(0x12c012c),
        UINT32_C(0x7fff),UINT32_C(0x10e),UINT32_C(0x1ab02f6),UINT32_C(0x30205),UINT32_C(0x0),UINT32_C(0x525),UINT32_C(0x101),UINT32_C(0x60301),
        UINT32_C(0x0),UINT32_C(0x40040600),UINT32_C(0x4080808),UINT32_C(0x40010),UINT32_C(0x0),UINT32_C(0x1f0000),UINT32_C(0x1f100804),UINT32_C(0x32001e),
        UINT32_C(0x3c0010),UINT32_C(0x640fff),UINT32_C(0xa1f0c0e),UINT32_C(0x4000000),UINT32_C(0x8080808),UINT32_C(0x808),UINT32_C(0xaf00020),UINT32_C(0x0),
        UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),
        UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),
        UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),
        UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),UINT32_C(0x0),
    };
    if(!r) return false;
    for(unsigned i=0;i<sizeof(fields)/sizeof(fields[0]);i++)
        if(r[fields[i].offset/4]!=fields[i].value) return false;
    for(unsigned i=0;i<sizeof(opaque)/sizeof(opaque[0]);i++)
        if(r[0x500/4+i]!=opaque[i]) return false;
    return true;
}

static inline bool z62_video_port_profile(unsigned port,const uint32_t *r)
{
    static const struct {unsigned w,h,stride,uv;} shapes[]={
        {1920,1080,1920,0x33b900},{1024,576,1024,0x12d400},
        {1024,576,1024,0xc1000},{1508,846,1520,1285920}
    };
    unsigned i=port==8 ? 3 : port>=3 && port<=5 ? port-3 : 4;
    if(i>=4 || !r) return false;
    for(unsigned n=0;n<13;n++) {
        uint32_t expected=0;
        if(n==0) expected=0x09000201;
        if(n==1) expected=0x15500;
        if(n==4 || n==5) expected=shapes[i].stride;
        if(n==8) expected=(shapes[i].h<<16)|shapes[i].w;
        if(n==10) expected=shapes[i].uv;
        if(r[n]!=expected) return false;
    }
    return true;
}
#endif
