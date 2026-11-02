/* SPDX-License-Identifier: GPL-2.0-or-later
 * Functional preview approximation, not Nikon's proprietary ISP math.
 * Packed12 RGGB hypothesis -> 2-pixel crop -> CFA-cell RGB -> sRGB -> NV12.
 * Pure pixel code: no guest memory, GUI, register or IRQ access.
 */
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <math.h>
#include <glib.h>

#define Z62_PREVIEW_WIDTH 1514u
#define Z62_PREVIEW_HEIGHT 1006u
#define Z62_PREVIEW_STRIDE 2272u
#define Z62_PREVIEW_RAW_BYTES (Z62_PREVIEW_STRIDE * Z62_PREVIEW_HEIGHT)

typedef struct Z62PreviewOutput {
    unsigned width, height, stride;
    uint8_t *data;
} Z62PreviewOutput;

typedef struct Z62PreviewPixels {
    uint8_t *raw;
    uint8_t tone[4096];
    Z62PreviewOutput output[3];
    uint64_t hits, misses, input_changes;
} Z62PreviewPixels;

static Z62PreviewPixels *z62_preview_pixels_new(void)
{
    Z62PreviewPixels *p = g_new0(Z62PreviewPixels, 1);
    for (unsigned i = 0; i < 4096; i++) {
        double value = CLAMP(((double)i - 64) / (4095 - 64), 0, 1);
        value = value <= 0.0031308 ? 12.92*value : 1.055*pow(value, 1.0/2.4)-0.055;
        p->tone[i] = CLAMP(lrint(value*255), 0, 255);
    }
    return p;
}

static void z62_preview_pixels_input(Z62PreviewPixels *p, const uint8_t *raw)
{
    if (p->raw && !memcmp(p->raw, raw, Z62_PREVIEW_RAW_BYTES)) { return; }
    if (!p->raw) { p->raw = g_malloc(Z62_PREVIEW_RAW_BYTES); }
    memcpy(p->raw, raw, Z62_PREVIEW_RAW_BYTES);
    for (unsigned i = 0; i < 3; i++) { g_clear_pointer(&p->output[i].data, g_free); }
    p->input_changes++;
}

static unsigned z62_preview_raw(const uint8_t *raw, unsigned x, unsigned y)
{
    const uint8_t *sample = raw + y*Z62_PREVIEW_STRIDE + (x/2)*3;
    return x&1 ? (sample[1]>>4) | (sample[2]<<4) : sample[0] | ((sample[1]&15)<<8);
}

static const uint8_t *z62_preview_pixels_render(Z62PreviewPixels *p, unsigned channel,
                                               unsigned w, unsigned h, unsigned stride)
{
    if (!p->raw || channel >= 3 || !w || !h || (w&1) || (h&1) ||
        w > 1920 || h > 1080 || stride < w || stride > 2048) { return NULL; }
    Z62PreviewOutput *out = &p->output[channel];
    if (out->data && out->width == w && out->height == h && out->stride == stride) {
        p->hits++; return out->data;
    }
    p->misses++;
    g_free(out->data);
    size_t ybytes = (size_t)stride*h;
    out->data = g_malloc(ybytes + ybytes/2);
    out->width = w; out->height = h; out->stride = stride;
    uint8_t *yp = out->data, *uvp = out->data+ybytes;
    memset(yp, 16, ybytes); memset(uvp, 128, ybytes/2);
    unsigned xs[1920], ys[1080];
    for (unsigned x = 0; x < w; x++) { xs[x] = 2 + ((uint64_t)x*755/w)*2; }
    for (unsigned y = 0; y < h; y++) { ys[y] = 2 + ((uint64_t)y*501/h)*2; }
    for (unsigned y = 0; y < h; y += 2) {
        for (unsigned x = 0; x < w; x += 2) {
            unsigned sr = 0, sg = 0, sb = 0;
            for (unsigned dy = 0; dy < 2; dy++) {
                for (unsigned dx = 0; dx < 2; dx++) {
                    unsigned sx = xs[x+dx], sy = ys[y+dy];
                    unsigned red = p->tone[z62_preview_raw(p->raw, sx, sy)];
                    unsigned green = p->tone[(z62_preview_raw(p->raw, sx+1, sy) +
                                                z62_preview_raw(p->raw, sx, sy+1) + 1)/2];
                    unsigned blue = p->tone[z62_preview_raw(p->raw, sx+1, sy+1)];
                    yp[(y+dy)*stride+x+dx] = CLAMP(((66*red+129*green+25*blue+128)>>8)+16,16,235);
                    sr += red; sg += green; sb += blue;
                }
            }
            int red = (sr+2)/4, green = (sg+2)/4, blue = (sb+2)/4;
            uvp[(y/2)*stride+x] = CLAMP(((-38*red-74*green+112*blue+128)>>8)+128,16,240);
            uvp[(y/2)*stride+x+1] = CLAMP(((112*red-94*green-18*blue+128)>>8)+128,16,240);
        }
    }
    return out->data;
}

static void z62_preview_pixels_free(Z62PreviewPixels *p)
{
    if (!p) { return; }
    for (unsigned i = 0; i < 3; i++) { g_free(p->output[i].data); }
    g_free(p->raw); g_free(p);
}
