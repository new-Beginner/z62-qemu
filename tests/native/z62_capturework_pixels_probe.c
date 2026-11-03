/* SPDX-License-Identifier: GPL-2.0-or-later
 * Independent literal/decoded-bit and two-pass remainder-raster checks.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "nikon-z62-capturework-pixels.h"

#define CHECK(x) do { if (!(x)) { fprintf(stderr,"check failed at line %d: %s\n",__LINE__,#x); return 1; } } while (0)

static void put16(uint8_t *p, unsigned value)
{ p[0]=(uint8_t)value; p[1]=(uint8_t)(value>>8); }
static unsigned get16(const uint8_t *p)
{ return (unsigned)p[0]|(unsigned)p[1]<<8; }
static unsigned decode(const uint8_t *p,unsigned sample,unsigned bits)
{
    unsigned result=0;
    for (unsigned bit=0;bit<bits;bit++) {
        unsigned position=sample*bits+bit;
        result|=((unsigned)(p[position/8]>>(position%8))&1u)<<bit;
    }
    return result;
}
static Z62CaptureWorkPixelsConfig config(unsigned width,unsigned height,unsigned bits)
{
    Z62CaptureWorkPixelsConfig c={0};
    c.input_width=c.intermediate_width=c.output_width=width;
    c.input_height=c.intermediate_height=c.output_height=height;
    c.input_stride=2*width; c.output_stride=((width*bits/8+15)/16)*16; c.bits=(uint8_t)bits;
    return c;
}
static int golden(unsigned bits)
{
    uint8_t source[8]={0},output[32];
    Z62CaptureWorkPixelsConfig c=config(bits==14?4:2,1,bits);
    memset(output,0xa5,sizeof(output));
    if (bits==12) { put16(source,0x1230); put16(source+2,0x4560); }
    else if (bits==16) { put16(source,0x1234); put16(source+2,0xabcd); }
    else { put16(source,0x0123u<<2); put16(source+2,0x2345u<<2); put16(source+4,0x3fffu<<2); put16(source+6,0x0011u<<2); }
    CHECK(z62_capturework_pixels_pack(&c,source,sizeof(source),output,sizeof(output))==Z62_CW_PIXELS_OK);
    if (bits==12) { const uint8_t expected[]={0x23,0x61,0x45}; CHECK(!memcmp(output,expected,sizeof(expected))); }
    if (bits==16) { const uint8_t expected[]={0x34,0x12,0xcd,0xab}; CHECK(!memcmp(output,expected,sizeof(expected))); }
    for (unsigned x=0;x<c.output_width;x++) CHECK(decode(output,x,bits)==(get16(source+2*x)>>(16-bits)));
    unsigned payload=c.output_width*bits/8;
    for (unsigned i=payload;i<sizeof(output);i++) CHECK(output[i]==0xa5);
    return 0;
}

/* Materialize two distinct tile images with increment/remainder addressing.
 * The core instead composes two integer coordinate quotients directly.
 */
static void reference_resize(const uint8_t *source,unsigned sw,unsigned sh,unsigned ss,
                             uint8_t *dest,unsigned dw,unsigned dh,int cfa)
{
    unsigned tile=cfa?2u:1u,srcw=sw/tile,srch=sh/tile,dstw=dw/tile,dsth=dh/tile;
    unsigned sy=0,y_remainder=0;
    for (unsigned y=0;y<dsth;y++) {
        unsigned sx=0,x_remainder=0;
        for (unsigned x=0;x<dstw;x++) {
            for (unsigned dy=0;dy<tile;dy++) for (unsigned dx=0;dx<tile;dx++)
                memcpy(dest+2*((size_t)(tile*y+dy)*dw+tile*x+dx),
                       source+(size_t)(tile*sy+dy)*ss+2*(tile*sx+dx),2);
            x_remainder+=srcw;
            while (x_remainder>=dstw) { x_remainder-=dstw; sx++; }
        }
        y_remainder+=srch;
        while (y_remainder>=dsth) { y_remainder-=dsth; sy++; }
    }
}

static int rational(int cfa)
{
    uint8_t source[14*14*2],mid[10*10*2],expected[6*6*2],output[6*16];
    Z62CaptureWorkPixelsConfig c=config(14,14,16);
    c.intermediate_width=c.intermediate_height=10;
    c.output_width=c.output_height=6; c.output_stride=16; c.cfa=(uint8_t)cfa;
    for (unsigned y=0;y<14;y++) for (unsigned x=0;x<14;x++) put16(source+2*(y*14+x),y*16+x);
    memset(output,0xa5,sizeof(output));
    reference_resize(source,14,14,28,mid,10,10,cfa);
    reference_resize(mid,10,10,20,expected,6,6,cfa);
    CHECK(z62_capturework_pixels_pack(&c,source,sizeof(source),output,sizeof(output))==Z62_CW_PIXELS_OK);
    for (unsigned y=0;y<6;y++) {
        for (unsigned x=0;x<6;x++) CHECK(decode(output+y*16,x,16)==get16(expected+2*(y*6+x)));
        for (unsigned x=12;x<16;x++) CHECK(output[y*16+x]==0xa5);
    }
    if (cfa) {
        const unsigned positions[]={0,1,2,3,8,9};
        for (unsigned x=0;x<6;x++) CHECK(decode(output,x,16)==positions[x]);
        CHECK(decode(output,2,16)!=4); /* direct single-stage nearest differs */
    }
    return 0;
}

static int lookup(void)
{
    uint8_t source[8],output[32]; uint16_t lut[256];
    for (unsigned i=0;i<256;i++) lut[i]=(uint16_t)(i*16);
    Z62CaptureWorkPixelsConfig c=config(4,1,12); c.use_lut=1; c.lookup=lut;
    put16(source,0x0000); put16(source+2,0x10ff); put16(source+4,0xfe01); put16(source+6,0xffff);
    memset(output,0xa5,sizeof(output));
    CHECK(z62_capturework_pixels_pack(&c,source,sizeof(source),output,sizeof(output))==Z62_CW_PIXELS_OK);
    const unsigned expected[]={0,256,4064,4080};
    for (unsigned i=0;i<4;i++) CHECK(decode(output,i,12)==expected[i]);
    lut[200]=lut[199]; memset(output,0xa5,sizeof(output));
    CHECK(z62_capturework_pixels_pack(&c,source,sizeof(source),output,sizeof(output))==Z62_CW_PIXELS_LUT);
    for (unsigned i=0;i<sizeof(output);i++) CHECK(output[i]==0xa5);
    lut[200]=4096;
    CHECK(z62_capturework_pixels_pack(&c,source,sizeof(source),output,sizeof(output))==Z62_CW_PIXELS_LUT);
    for (unsigned i=0;i<sizeof(output);i++) CHECK(output[i]==0xa5);
    return 0;
}

static int padding(void)
{
    uint8_t source[16],before[16],output[24];
    Z62CaptureWorkPixelsConfig c=config(2,2,16); c.input_stride=8; c.output_stride=8; c.cfa=1;
    memset(source,0xee,sizeof(source)); memset(output,0xa5,sizeof(output));
    put16(source,0x1234); put16(source+2,0xabcd); put16(source+8,0x5678); put16(source+10,0x9abc);
    memcpy(before,source,sizeof(source));
    CHECK(z62_capturework_pixels_pack(&c,source,sizeof(source),output,sizeof(output))==Z62_CW_PIXELS_OK);
    CHECK(get16(output)==0x1234 && get16(output+2)==0xabcd && get16(output+8)==0x5678 && get16(output+10)==0x9abc);
    for (unsigned i=0;i<sizeof(output);i++) if (i>=16 || i%8>=4) CHECK(output[i]==0xa5);
    CHECK(!memcmp(source,before,sizeof(source)));
    return 0;
}

static int rejects(void)
{
    uint8_t source[64]={0},output[64]; Z62CaptureWorkPixelsConfig base=config(4,2,12);
    for (unsigned mode=0;mode<14;mode++) {
        Z62CaptureWorkPixelsConfig c=base; size_t input=sizeof(source),out=sizeof(output);
        if (mode==0) c.input_width=0;
        if (mode==1) c.intermediate_width=5;
        if (mode==2) c.output_height=3;
        if (mode==3) c.bits=10;
        if (mode==4) c.input_stride=7;
        if (mode==5) c.output_stride=5;
        if (mode==6) input=1;
        if (mode==7) out=1;
        if (mode==8) c.cfa=1,c.output_width=3;
        if (mode==9) c.correction_flags=1;
        if (mode==10) c.input_stride=UINT32_MAX;
        if (mode==11) c.output_stride=UINT32_MAX;
        if (mode==12) c.input_width=4096,c.input_height=4096;
        if (mode==13) c.use_lut=1,c.lookup=NULL;
        memset(output,0xa5,sizeof(output));
        CHECK(z62_capturework_pixels_pack(&c,source,input,output,out)!=Z62_CW_PIXELS_OK);
        for (unsigned i=0;i<sizeof(output);i++) CHECK(output[i]==0xa5);
    }
    uint8_t before[64]; memset(source,0x5a,sizeof(source)); memcpy(before,source,sizeof(source));
    CHECK(z62_capturework_pixels_pack(&base,source,sizeof(source),source+2,32)==Z62_CW_PIXELS_OVERLAP);
    CHECK(!memcmp(source,before,sizeof(source)));
    return 0;
}

static int live(int argc,char **argv)
{
    CHECK(argc==12);
    Z62CaptureWorkPixelsConfig c={0};
    c.input_width=(unsigned)strtoul(argv[2],NULL,10); c.input_height=(unsigned)strtoul(argv[3],NULL,10);
    c.intermediate_width=(unsigned)strtoul(argv[4],NULL,10); c.intermediate_height=(unsigned)strtoul(argv[5],NULL,10);
    c.output_width=(unsigned)strtoul(argv[6],NULL,10); c.output_height=(unsigned)strtoul(argv[7],NULL,10);
    c.bits=(uint8_t)strtoul(argv[8],NULL,10); c.output_stride=(unsigned)strtoul(argv[9],NULL,10);
    c.input_stride=2*c.input_width; c.cfa=1; c.use_lut=1; uint16_t lut[256]; char *position=argv[10];
    for (unsigned i=0;i<256;i++) {
        char *end; unsigned long value=strtoul(position,&end,10); CHECK(end!=position && value<=65535);
        lut[i]=(uint16_t)value;
        CHECK(i==255?*end=='\0':*end==','); position=end+1;
    }
    c.lookup=lut;
    size_t input_size=(size_t)c.input_stride*c.input_height,output_size=(size_t)c.output_stride*c.output_height;
    CHECK(input_size<=64u*1024*1024 && output_size<=64u*1024*1024);
    Z62CaptureWorkPixelsPlan preflight;
    CHECK(z62_capturework_pixels_plan(&c,input_size,output_size,&preflight)==Z62_CW_PIXELS_OK);
    uint8_t *source=malloc(input_size),*output=malloc(output_size);
    uint8_t *mid=malloc((size_t)c.intermediate_width*c.intermediate_height*2);
    uint8_t *expected=malloc((size_t)c.output_width*c.output_height*2);
    CHECK(source && output && mid && expected);
    for (unsigned y=0;y<c.input_height;y++) for (unsigned x=0;x<c.input_width;x++)
        put16(source+(size_t)y*c.input_stride+2*x,((x*3+y*5+17)&255u)*256u+((x+y)&255u));
    memset(output,0xa5,output_size);
    CHECK(z62_capturework_pixels_pack(&c,source,input_size,output,output_size)==Z62_CW_PIXELS_OK);
    reference_resize(source,c.input_width,c.input_height,c.input_stride,mid,c.intermediate_width,c.intermediate_height,1);
    reference_resize(mid,c.intermediate_width,c.intermediate_height,2*c.intermediate_width,expected,c.output_width,c.output_height,1);
    for (unsigned y=0;y<c.output_height;y++) {
        for (unsigned x=0;x<c.output_width;x++) CHECK(decode(output+(size_t)y*c.output_stride,x,c.bits)==
            lut[get16(expected+2*((size_t)y*c.output_width+x))>>8]);
        for (unsigned x=c.output_width*c.bits/8;x<c.output_stride;x++) CHECK(output[(size_t)y*c.output_stride+x]==0xa5);
    }
    FILE *file=fopen(argv[11],"wb"); CHECK(file!=NULL);
    CHECK(fwrite(output,1,output_size,file)==output_size); CHECK(fclose(file)==0);
    printf("{\"completed\":true,\"pixels_checked\":%u,\"output_bytes\":%zu,\"padding_preserved\":true,\"independent_two_pass_reference\":true}\n",
           c.output_width*c.output_height,output_size);
    free(source); free(output); free(mid); free(expected);
    return 0;
}

int main(int argc,char **argv)
{
    CHECK(argc>=2);
    if (!strcmp(argv[1],"live")) return live(argc,argv);
    int result=1;
    if (!strcmp(argv[1],"raw12")) result=golden(12);
    else if (!strcmp(argv[1],"raw14")) result=golden(14);
    else if (!strcmp(argv[1],"raw16")) result=golden(16);
    else if (!strcmp(argv[1],"rational-mono")) result=rational(0);
    else if (!strcmp(argv[1],"rational-cfa")) result=rational(1);
    else if (!strcmp(argv[1],"lookup")) result=lookup();
    else if (!strcmp(argv[1],"padding")) result=padding();
    else if (!strcmp(argv[1],"rejects")) result=rejects();
    if (!result) printf("{\"completed\":true,\"case\":\"%s\"}\n",argv[1]);
    return result;
}
