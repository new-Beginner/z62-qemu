/* SPDX-License-Identifier: GPL-2.0-or-later
 * Explicit C video MAIN / two-plane WORK / preview approximation.
 * No guest address, lifecycle, status, event or IRQ access.
 */
#ifndef NIKON_Z62_VIDEO_PIXELS_H
#define NIKON_Z62_VIDEO_PIXELS_H
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include "nikon-z62-video-source-pixels.h"

#define Z62_VIDEO_MAIN_WIDTH 1508u
#define Z62_VIDEO_MAIN_HEIGHT 846u
#define Z62_VIDEO_MAIN_STRIDE 1520u
#define Z62_VIDEO_MAIN_Y_BYTES (1520u*846u)
#define Z62_VIDEO_MAIN_BYTES (Z62_VIDEO_MAIN_Y_BYTES*3/2)
#define Z62_VIDEO_WORK_BYTES (1520u*423u)
#define Z62_VIDEO_INPUT_BYTES (2272u*1006u)

typedef struct Z62VideoOutput { uint8_t *data; unsigned width,height,stride; } Z62VideoOutput;
typedef struct Z62VideoPixels {
    uint8_t tone[4096];
    uint8_t *source,*view,*main,*work;
    int origin_x,origin_y;
    Z62VideoOutput output[3];
} Z62VideoPixels;

static inline unsigned z62_video_clip(int value,unsigned low,unsigned high)
{ return value<(int)low ? low : value>(int)high ? high : (unsigned)value; }

static inline Z62VideoPixels *z62_video_pixels_new(void)
{
    Z62VideoPixels *p=calloc(1,sizeof(*p));
    if(!p) return NULL;
    for(unsigned i=0;i<4096;i++) {
        double v=((double)i-64)/(4095-64);
        if(v<0) v=0;
        v=v<=0.0031308 ? 12.92*v : 1.055*pow(v,1.0/2.4)-0.055;
        p->tone[i]=(uint8_t)z62_video_clip((int)lrint(v*255),0,255);
    }
    return p;
}

static inline void z62_video_pixels_free(Z62VideoPixels *p)
{
    if(!p) return;
    for(unsigned i=0;i<3;i++) free(p->output[i].data);
    free(p->source);free(p->view);free(p->main);free(p->work);free(p);
}

static inline unsigned z62_video_sample(const uint8_t *raw,unsigned x,unsigned y)
{
    const uint8_t *p=raw+(size_t)y*2288+x/2*3;
    return x&1 ? (p[1]>>4)|(unsigned)p[2]<<4 : p[0]|(unsigned)(p[1]&15)<<8;
}

static inline void z62_video_u16(uint8_t *p,uint16_t value)
{ p[0]=(uint8_t)value;p[1]=(uint8_t)(value>>8); }

static inline bool z62_video_pixels_input(Z62VideoPixels *p,const uint8_t *raw,size_t size,int x,int y)
{
    if(!p || !raw || size<Z62_VIDEO_INPUT_BYTES || x%2 || y%2 || x < -4096 ||
       x>4096 || y < -4096 || y>4096) return false;
    if(p->source && p->origin_x==x && p->origin_y==y && !memcmp(p->source,raw,Z62_VIDEO_INPUT_BYTES)) return true;
    uint8_t *source=malloc(Z62_VIDEO_INPUT_BYTES),*view=calloc(2288u*854u,1);
    uint8_t *main=malloc(Z62_VIDEO_MAIN_BYTES),*work=calloc(2*Z62_VIDEO_WORK_BYTES,1);
    if(!source || !view || !main || !work) { free(source);free(view);free(main);free(work);return false; }
    memcpy(source,raw,Z62_VIDEO_INPUT_BYTES);
    if(!z62_video_raw_view(source,Z62_VIDEO_INPUT_BYTES,1514,1006,2272,view,2288u*854u,1516,854,2288,x,y)) {
        free(source);free(view);free(main);free(work);return false;
    }
    memset(main,16,Z62_VIDEO_MAIN_Y_BYTES);memset(main+Z62_VIDEO_MAIN_Y_BYTES,128,Z62_VIDEO_MAIN_Y_BYTES/2);
    for(unsigned cy=0;cy<423;cy++) for(unsigned cx=0;cx<754;cx++) {
        unsigned sx=4+cx*2,sy=4+cy*2;
        unsigned r=z62_video_sample(view,sx,sy),g1=z62_video_sample(view,sx+1,sy);
        unsigned g2=z62_video_sample(view,sx,sy+1),b=z62_video_sample(view,sx+1,sy+1);
        unsigned red=p->tone[r],green=p->tone[(g1+g2+1)/2],blue=p->tone[b];
        uint8_t luma=(uint8_t)z62_video_clip((int)((66*red+129*green+25*blue+128)>>8)+16,16,235);
        uint8_t *yp=main+(size_t)(cy*2)*1520+cx*2;
        yp[0]=yp[1]=yp[1520]=yp[1521]=luma;
        uint8_t *uv=main+Z62_VIDEO_MAIN_Y_BYTES+(size_t)cy*1520+cx*2;
        uv[0]=(uint8_t)z62_video_clip(((-38*(int)red-74*(int)green+112*(int)blue+128)>>8)+128,16,240);
        uv[1]=(uint8_t)z62_video_clip(((112*(int)red-94*(int)green-18*(int)blue+128)>>8)+128,16,240);
        /* Explicit WORK proxies: linear CFA mean and signed RB-minus-G.
         * They are computed data, not recovered temporal history or PDAF. */
        size_t off=(size_t)cy*1520+cx*2;
        z62_video_u16(work+off,(uint16_t)((r+g1+g2+b+2)/4));
        int residual=(int)((r+b+1)/2)-(int)((g1+g2+1)/2);
        z62_video_u16(work+Z62_VIDEO_WORK_BYTES+off,(uint16_t)residual);
    }
    free(p->source);free(p->view);free(p->main);free(p->work);
    p->source=source;p->view=view;p->main=main;p->work=work;p->origin_x=x;p->origin_y=y;
    for(unsigned i=0;i<3;i++) { free(p->output[i].data);p->output[i].data=NULL; }
    return true;
}

static inline const uint8_t *z62_video_pixels_render(Z62VideoPixels *p,unsigned channel,unsigned w,unsigned h,unsigned stride)
{
    if(!p || !p->main || channel>=3 || !w || !h || ((w|h)&1) || w>1920 || h>1080 || stride<w || stride>2048) return NULL;
    Z62VideoOutput *out=&p->output[channel];
    if(out->data && out->width==w && out->height==h && out->stride==stride) return out->data;
    size_t bytes=(size_t)stride*h;
    uint8_t *pixels=malloc(bytes+bytes/2);
    if(!pixels) return NULL;
    memset(pixels,16,bytes);memset(pixels+bytes,128,bytes/2);
    for(unsigned y=0;y<h;y++) {
        unsigned sy=(uint64_t)y*846/h;
        for(unsigned x=0;x<w;x++) {
            unsigned sx=(uint64_t)x*1508/w;
            pixels[(size_t)y*stride+x]=p->main[(size_t)sy*1520+sx];
        }
    }
    for(unsigned y=0;y<h/2;y++) {
        unsigned sy=(uint64_t)y*423/(h/2);
        for(unsigned x=0;x<w;x+=2) {
            unsigned sx=((uint64_t)(x/2)*754/(w/2))*2;
            const uint8_t *uv=p->main+Z62_VIDEO_MAIN_Y_BYTES+(size_t)sy*1520+sx;
            pixels[bytes+(size_t)y*stride+x]=uv[0];pixels[bytes+(size_t)y*stride+x+1]=uv[1];
        }
    }
    free(out->data);out->data=pixels;out->width=w;out->height=h;out->stride=stride;
    return pixels;
}
#endif
