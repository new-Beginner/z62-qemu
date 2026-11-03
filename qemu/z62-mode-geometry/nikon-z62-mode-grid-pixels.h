/* SPDX-License-Identifier: GPL-2.0-or-later
 * Geometry-aware C software operator, not Nikon's proprietary grid algorithm.
 * Device admission, source freshness, DMA and completion remain separate.
 */
#ifndef NIKON_Z62_MODE_GRID_PIXELS_H
#define NIKON_Z62_MODE_GRID_PIXELS_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

static inline unsigned z62_mode_grid_u16(const uint8_t *p)
{
    return p[0] | (unsigned)p[1] << 8;
}

static inline bool z62_mode_grid_convert(const uint8_t *const plane[3],
                                         const size_t available[3],
                                         unsigned width, unsigned height,
                                         const size_t row[3], uint8_t *out,
                                         size_t output_bytes, size_t output_row)
{
    size_t extent[3];
    uintptr_t destination = (uintptr_t)out;
    if (!plane || !available || !row || !out || !width || (width & 1) ||
        width > 4096 || !height || height > 4096 ||
        output_row < (size_t)width/2*3 || output_row > 65536 ||
        output_row > SIZE_MAX/height || output_bytes < output_row*height ||
        destination > UINTPTR_MAX-output_row*height) {
        return false;
    }
    size_t output_span = output_row*height;
    for (unsigned c=0; c<3; c++) {
        uintptr_t source = (uintptr_t)plane[c];
        if (!plane[c] || row[c] < (size_t)width*2 || row[c] > 65536 ||
            row[c] > SIZE_MAX/height) { return false; }
        extent[c] = row[c]*height;
        if (available[c] < extent[c] || source > UINTPTR_MAX-extent[c] ||
            (source < destination+output_span && destination < source+extent[c])) {
            return false;
        }
    }
    for (unsigned c=0; c<3; c++) {
        for (unsigned y=0; y<height; y++) {
            for (unsigned x=0; x<width; x++) {
                if (z62_mode_grid_u16(plane[c]+y*row[c]+x*2) > 4095) { return false; }
            }
        }
    }
    /* No output, including row padding, changes until every sample is legal. */
    memset(out, 0, output_span);
    for (unsigned y=0; y<height; y++) {
        for (unsigned x=0; x<width; x+=2) {
            unsigned sum[2] = {0, 0};
            for (unsigned c=0; c<3; c++) {
                sum[0] += z62_mode_grid_u16(plane[c]+y*row[c]+x*2);
                sum[1] += z62_mode_grid_u16(plane[c]+y*row[c]+(x+1)*2);
            }
            unsigned a = (sum[0]+1)/3, b = (sum[1]+1)/3;
            uint8_t *p = out+y*output_row+(x/2)*3;
            p[0] = a;
            p[1] = (a>>8) | ((b&15)<<4);
            p[2] = b>>4;
        }
    }
    return true;
}
#endif
