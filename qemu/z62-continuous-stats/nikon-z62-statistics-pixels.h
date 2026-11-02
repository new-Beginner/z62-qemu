/* SPDX-License-Identifier: GPL-2.0-or-later
 * Functional statistics for a stationary packed12 RGGB input scene.
 * Layouts are from original C1.70 CPU loads and DMA descriptors. Arithmetic
 * is an explicit regional-mean hypothesis, not Nikon calibration/AE math.
 * The observed fixed grids cover this available RAW scene proportionally;
 * sensor-space crop, threshold rejection and color calibration are not modeled.
 */
#ifndef NIKON_Z62_STATISTICS_PIXELS_H
#define NIKON_Z62_STATISTICS_PIXELS_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

#define Z62_STATS_RAW_W 1514u
#define Z62_STATS_RAW_H 1006u
#define Z62_STATS_RAW_STRIDE 2272u
#define Z62_STATS_RAW_BYTES (Z62_STATS_RAW_STRIDE * Z62_STATS_RAW_H)

typedef struct Z62StatisticsPixels {
    uint8_t sums[480 * 20];       /* Three LE-u32 channel sums, LE-u32 count. */
    uint8_t scalar[64 * 20];      /* 30 LE-u16 values per row plus padding. */
    uint8_t rgb[3][128 * 40];     /* 60 LE-u16 values per row plus padding. */
} Z62StatisticsPixels;

static unsigned z62_stats_raw_pixel(const uint8_t *raw, unsigned x, unsigned y)
{
    const uint8_t *p = raw + y*Z62_STATS_RAW_STRIDE + (x/2)*3;
    return (x & 1) ? (p[1] >> 4) | ((unsigned)p[2] << 4) : p[0] | ((p[1] & 15u) << 8);
}

static void z62_stats_put16(uint8_t *p, unsigned value)
{
    p[0] = value;
    p[1] = value >> 8;
}

static void z62_stats_put32(uint8_t *p, uint32_t value)
{
    p[0] = value;
    p[1] = value >> 8;
    p[2] = value >> 16;
    p[3] = value >> 24;
}

static void z62_stats_box(const uint8_t *raw, unsigned x, unsigned y,
                          unsigned width, unsigned height, uint64_t sum[3],
                          uint64_t *total, unsigned *count)
{
    unsigned x0 = x*(Z62_STATS_RAW_W/2)/width;
    unsigned x1 = (x+1)*(Z62_STATS_RAW_W/2)/width;
    unsigned y0 = y*(Z62_STATS_RAW_H/2)/height;
    unsigned y1 = (y+1)*(Z62_STATS_RAW_H/2)/height;
    sum[0] = sum[1] = sum[2] = 0;
    *total = 0;
    *count = (x1-x0)*(y1-y0);
    for (unsigned sy = y0; sy < y1; sy++) {
        for (unsigned sx = x0; sx < x1; sx++) {
            unsigned r = z62_stats_raw_pixel(raw, sx*2, sy*2);
            unsigned g1 = z62_stats_raw_pixel(raw, sx*2+1, sy*2);
            unsigned g2 = z62_stats_raw_pixel(raw, sx*2, sy*2+1);
            unsigned b = z62_stats_raw_pixel(raw, sx*2+1, sy*2+1);
            sum[0] += r;
            sum[1] += (g1+g2+1)/2;
            sum[2] += b;
            *total += r+g1+g2+b;
        }
    }
}

static bool z62_statistics_calculate(const uint8_t *raw, size_t bytes,
                                     Z62StatisticsPixels *out)
{
    if (!raw || !out || bytes < Z62_STATS_RAW_BYTES) {
        return false;
    }
    uintptr_t src = (uintptr_t)raw, dst = (uintptr_t)out;
    if (src > UINTPTR_MAX-Z62_STATS_RAW_BYTES || dst > UINTPTR_MAX-sizeof(*out) ||
        (src < dst+sizeof(*out) && dst < src+Z62_STATS_RAW_BYTES)) {
        return false;
    }
    memset(out, 0, sizeof(*out));
    for (unsigned y = 0; y < 20; y++) {
        for (unsigned x = 0; x < 30; x++) {
            uint64_t sum[3], total;
            unsigned count;
            z62_stats_box(raw, x, y, 30, 20, sum, &total, &count);
            uint8_t *p = out->sums + y*480 + x*16;
            for (unsigned c = 0; c < 3; c++) { z62_stats_put32(p+c*4, (uint32_t)sum[c]); }
            z62_stats_put32(p+12, count);
            z62_stats_put16(out->scalar+y*64+x*2, (unsigned)((total+2*count)/(4*count)));
        }
    }
    for (unsigned y = 0; y < 40; y++) {
        for (unsigned x = 0; x < 60; x++) {
            uint64_t sum[3], total;
            unsigned count;
            z62_stats_box(raw, x, y, 60, 40, sum, &total, &count);
            for (unsigned c = 0; c < 3; c++) {
                z62_stats_put16(out->rgb[c]+y*128+x*2, (unsigned)((sum[c]+count/2)/count));
            }
        }
    }
    return true;
}
#endif
