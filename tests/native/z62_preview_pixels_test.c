/* Pure native pixel math, no QEMU guest/firmware or physical camera. */
#include <assert.h>
#include <stdio.h>
#include "../../qemu/z62-preview/nikon-z62-preview-pixels.h"

static void scene(uint8_t *raw, unsigned r, unsigned g, unsigned b)
{
    memset(raw, 0, Z62_PREVIEW_RAW_BYTES);
    for (unsigned y=0;y<Z62_PREVIEW_HEIGHT;y++) {
        for (unsigned x=0;x<Z62_PREVIEW_WIDTH;x+=2) {
            unsigned a=y&1 ? g:r, z=y&1 ? b:g;
            uint8_t *p=raw+y*Z62_PREVIEW_STRIDE+(x/2)*3;
            p[0]=a; p[1]=(a>>8)|((z&15)<<4); p[2]=z>>4;
        }
    }
}

int main(void)
{
    Z62PreviewPixels *p=z62_preview_pixels_new();
    uint8_t *raw=g_malloc(Z62_PREVIEW_RAW_BYTES);
    assert(!z62_preview_pixels_render(p,0,4,4,8));
    scene(raw,64,64,64);
    z62_preview_pixels_input(p,raw);
    const uint8_t *out=z62_preview_pixels_render(p,0,4,4,8);
    for(unsigned i=0;i<32;i++) { assert(out[i]==16); }
    for(unsigned i=32;i<48;i++) { assert(out[i]==128); }
    scene(raw,4095,4095,4095);
    z62_preview_pixels_input(p,raw);
    out=z62_preview_pixels_render(p,0,4,4,8);
    for(unsigned y=0;y<4;y++) {
        for(unsigned x=0;x<8;x++) { assert(out[y*8+x]==(x<4 ? 235:16)); }
    }
    for(unsigned i=32;i<48;i++) { assert(out[i]==128); }
    scene(raw,4095,64,64);
    z62_preview_pixels_input(p,raw);
    out=z62_preview_pixels_render(p,1,4,4,4);
    for(unsigned i=0;i<16;i++) { assert(out[i]==82); }
    for(unsigned i=16;i<24;i+=2) { assert(out[i]==90 && out[i+1]==240); }
    uint64_t changes=p->input_changes,misses=p->misses;
    z62_preview_pixels_input(p,raw);
    assert(z62_preview_pixels_render(p,1,4,4,4)==out);
    assert(p->input_changes==changes && p->misses==misses && p->hits==1);
    assert(!z62_preview_pixels_render(p,3,4,4,4));
    assert(!z62_preview_pixels_render(p,0,3,4,4));
    assert(!z62_preview_pixels_render(p,0,4,3,4));
    assert(!z62_preview_pixels_render(p,0,4,4,3));
    assert(!z62_preview_pixels_render(p,0,1922,1080,2048));
    /* The ignored 2-pixel outer border must not change a solid cropped image. */
    raw[0]^=0xff;
    z62_preview_pixels_input(p,raw);
    out=z62_preview_pixels_render(p,1,4,4,4);
    assert(out[0]==82 && p->input_changes==changes+1);
    assert(z62_preview_pixels_render(p,2,1920,1080,1920));
    z62_preview_pixels_free(p); g_free(raw);
    puts("PASS: packed12 RGGB colors, NV12 levels/padding, crop, cache, bounds");
    return 0;
}
