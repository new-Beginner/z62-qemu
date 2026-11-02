/* SPDX-License-Identifier: GPL-2.0-or-later
 * Explicit C-level bank0 numerical substitute, not Nikon's matrix/LUT math.
 * Read three actual 60x40 LE-u16 planes and encode their rounded mean as RAW12.
 */
#ifndef NIKON_Z62_GRID_PIXELS_H
#define NIKON_Z62_GRID_PIXELS_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

#define Z62_GRID_W 60u
#define Z62_GRID_H 40u
#define Z62_GRID_SRC_ROW 128u
#define Z62_GRID_DST_ROW 96u
#define Z62_GRID_SRC_BYTES (Z62_GRID_SRC_ROW * Z62_GRID_H)
#define Z62_GRID_DST_BYTES (Z62_GRID_DST_ROW * Z62_GRID_H)

static inline unsigned z62_grid_u16(const uint8_t *p)
{
    return p[0] | (unsigned)p[1] << 8;
}

static inline bool z62_grid_convert(const uint8_t *r, const uint8_t *g, const uint8_t *b,
                                    size_t bytes, uint8_t *out, size_t output_bytes)
{
    const uint8_t *input[3] = {r,g,b};
    uintptr_t dst = (uintptr_t)out;
    if (!r || !g || !b || !out || bytes < Z62_GRID_SRC_BYTES ||
        output_bytes < Z62_GRID_DST_BYTES || dst > UINTPTR_MAX-Z62_GRID_DST_BYTES) {
        return false;
    }
    for (unsigned c = 0; c < 3; c++) {
        uintptr_t src = (uintptr_t)input[c];
        if (src > UINTPTR_MAX-Z62_GRID_SRC_BYTES ||
            (src < dst+Z62_GRID_DST_BYTES && dst < src+Z62_GRID_SRC_BYTES)) {
            return false;
        }
        for (unsigned y = 0; y < Z62_GRID_H; y++) {
            for (unsigned x = 0; x < Z62_GRID_W; x++) {
                if (z62_grid_u16(input[c]+y*Z62_GRID_SRC_ROW+x*2) > 4095) {
                    return false;
                }
            }
        }
    }
    /* Preflight all samples before changing even the first output byte. */
    memset(out,0,Z62_GRID_DST_BYTES);
    for (unsigned y = 0; y < Z62_GRID_H; y++) {
        for (unsigned x = 0; x < Z62_GRID_W; x += 2) {
            unsigned value[2] = {0,0};
            for (unsigned c = 0; c < 3; c++) {
                value[0] += z62_grid_u16(input[c]+y*Z62_GRID_SRC_ROW+x*2);
                value[1] += z62_grid_u16(input[c]+y*Z62_GRID_SRC_ROW+(x+1)*2);
            }
            unsigned a=(value[0]+1)/3, z=(value[1]+1)/3;
            uint8_t *p=out+y*Z62_GRID_DST_ROW+(x/2)*3;
            p[0]=a; p[1]=(a>>8)|((z&15)<<4); p[2]=z>>4;
        }
    }
    return true;
}
#endif
