/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <stdio.h>
#include "../../qemu/z62-video-isp/nikon-z62-video-pixels.h"
#include "../../qemu/z62-video-isp/nikon-z62-video-profile.h"
#define CHECK(x) do { if(!(x)) { fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#x); return 1; } } while(0)

static void put(uint8_t *p,unsigned a,unsigned b) { p[0]=a;p[1]=(a>>8)|((b&15)<<4);p[2]=b>>4; }
static unsigned le16(const uint8_t *p) { return p[0]|(unsigned)p[1]<<8; }
static void fill(uint8_t *raw,unsigned mode)
{
    memset(raw,0,Z62_VIDEO_INPUT_BYTES);
    for(unsigned y=0;y<1006;y++) for(unsigned x=0;x<1514;x+=2) {
        unsigned c=mode==4 ? ((x<756 ? 0u:1u)+(y<502 ? 0u:2u)) : mode;
        unsigned red=c==0||c==3 ? 4095:64, green=c==1||c==3 ? 4095:64, blue=c==2||c==3 ? 4095:64;
        put(raw+(size_t)y*2272+x/2*3,y&1 ? green:red,y&1 ? blue:green);
    }
}
static int image(const uint8_t *p,unsigned w,unsigned h,unsigned stride,unsigned y,unsigned u,unsigned v)
{
    for(unsigned row=0;row<h;row++) for(unsigned x=0;x<stride;x++)
        if(p[(size_t)row*stride+x]!=(x<w ? y:16)) return 0;
    p+=(size_t)stride*h;
    for(unsigned row=0;row<h/2;row++) for(unsigned x=0;x<stride;x++)
        if(p[(size_t)row*stride+x]!=(x<w ? (x&1 ? v:u):128)) return 0;
    return 1;
}
static void word(uint8_t *p,unsigned off,uint32_t value)
{ for(unsigned j=0;j<4;j++) p[off+j]=(uint8_t)(value>>(j*8)); }

int main(void)
{
    Z62VideoPixels *p=z62_video_pixels_new(); uint8_t *raw=malloc(Z62_VIDEO_INPUT_BYTES);
    CHECK(p && raw); fill(raw,0);
    CHECK(z62_video_pixels_input(p,raw,Z62_VIDEO_INPUT_BYTES,0,76));
    CHECK(image(p->main,1508,846,1520,82,90,240));
    for(unsigned y=0;y<423;y++) for(unsigned x=0;x<1520;x+=2) {
        CHECK(le16(p->work+(size_t)y*1520+x)==(x<1508 ? 1072:0));
        CHECK(le16(p->work+Z62_VIDEO_WORK_BYTES+(size_t)y*1520+x)==(x<1508 ? 2016:0));
    }
    const unsigned widths[3]={1920,1024,1024}, heights[3]={1080,576,576};
    for(unsigned c=0;c<3;c++) {
        const uint8_t *out=z62_video_pixels_render(p,c,widths[c],heights[c],widths[c]);
        CHECK(out && image(out,widths[c],heights[c],widths[c],82,90,240));
    }
    fill(raw,3); /* Producer memory changes cannot mutate already-owned input. */
    CHECK(image(p->main,1508,846,1520,82,90,240));
    CHECK(!z62_video_pixels_input(p,raw,Z62_VIDEO_INPUT_BYTES-1,0,76));
    CHECK(!z62_video_pixels_input(p,raw,Z62_VIDEO_INPUT_BYTES,1,76));
    CHECK(image(p->main,1508,846,1520,82,90,240));
    CHECK(z62_video_pixels_input(p,raw,Z62_VIDEO_INPUT_BYTES,0,76));
    CHECK(image(p->main,1508,846,1520,235,128,128));
    for(unsigned c=0;c<3;c++) CHECK(image(z62_video_pixels_render(p,c,6,4,8),6,4,8,235,128,128));
    CHECK(!z62_video_pixels_render(p,3,6,4,8));
    CHECK(!z62_video_pixels_render(p,0,5,4,8));
    fill(raw,4); CHECK(z62_video_pixels_input(p,raw,Z62_VIDEO_INPUT_BYTES,0,76));
    const uint8_t *out=z62_video_pixels_render(p,0,1024,576,1024);
    const unsigned xs[]={0,1022,0,1022},ys[]={0,0,574,574};
    const uint8_t expected_y[]={82,144,41,235}, expected_u[]={90,54,240,128}, expected_v[]={240,34,110,128};
    for(unsigned i=0;i<4;i++) {
        CHECK(out[ys[i]*1024+xs[i]]==expected_y[i]);
        CHECK(out[1024*576+ys[i]/2*1024+xs[i]]==expected_u[i]);
        CHECK(out[1024*576+ys[i]/2*1024+xs[i]+1]==expected_v[i]);
    }
    /* Independent packet literals; only internal row count differs from photo. */
    for(unsigned i=0;i<3;i++) {
        uint8_t param[160]={0}, saved[160]; uint32_t r[6]={0,0,0x200087e0,0x88000,0xc2000000,0};
        static const struct {unsigned off;uint32_t value;} common[]={
            {0,0x110a0000},{0x1c,0xff010000},{0x28,0x11080040},{0x38,0x20002},
            {0x48,0x01110080},{0x4c,6},{0x58,0xff},{0x60,0xff},{0x74,0xff},{0x7c,0xff},
            {0x94,0x200087e0},{0x98,0x88000}};
        for(unsigned j=0;j<sizeof(common)/sizeof(common[0]);j++) word(param,common[j].off,common[j].value);
        word(param,4,(uint32_t[]){0x400000,0x70000,0x460000}[i]);
        word(param,12,0x10003+i); word(param,0x2c,(widths[i]-1)<<16);
        word(param,0x30,((i==0 ? 1088u:582u)-1)<<16);
        word(param,0x34,i==2 ? 0x400040:0x1000100); memcpy(saved,param,160);
        const uint32_t bits[]={0x20,1,0x40};
        CHECK(z62_video_result_mask(i,widths[i],heights[i],r,param)==bits[i]);
        CHECK(!memcmp(param,saved,160));
        param[0x60]^=1; CHECK(!z62_video_result_mask(i,widths[i],heights[i],r,param));
    }
    z62_video_pixels_free(p); free(raw);
    puts("PASS: actual MAIN NV12, two computed WORK planes, preview from MAIN, literal colors, owned input, captured video units");
    return 0;
}
