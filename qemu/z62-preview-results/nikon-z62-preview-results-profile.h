/* SPDX-License-Identifier: GPL-2.0-or-later
 * Bounded Z62 C1.70 output recipes observed in r47/config-1.
 * The callback and software event words at +8c/+90 are deliberately unused.
 */
#ifndef NIKON_Z62_PREVIEW_RESULTS_PROFILE_H
#define NIKON_Z62_PREVIEW_RESULTS_PROFILE_H
#include <stdbool.h>
#include <stdint.h>

#define Z62_PREVIEW_RESULTS_MASK UINT32_C(0x61)

static inline uint32_t z62_result_word(const uint8_t *p, unsigned offset)
{
    return (uint32_t)p[offset] | (uint32_t)p[offset + 1] << 8 |
           (uint32_t)p[offset + 2] << 16 | (uint32_t)p[offset + 3] << 24;
}

static inline uint32_t z62_preview_result_mask(unsigned index,
                                              uint32_t width, uint32_t height,
                                              const uint32_t *r, const uint8_t *p)
{
    static const struct {
        uint32_t width, height, crop, rows, scale, bit;
    } units[] = {
        {1920, 1080, 0x400000, 1108, 0x1000100, 0x20},
        {1024, 682,  0x70000,  700, 0x1000100, 0x01},
        {1024, 680, 0x460000,  698,  0x400040, 0x40}
    };
    static const struct { unsigned offset; uint32_t value; } profile[] = {
        {0, 0x110a0000}, {8, 0}, {0x10, 0}, {0x14, 0}, {0x18, 0},
        {0x1c, 0xff010000}, {0x20, 0}, {0x24, 0}, {0x28, 0x11080040},
        {0x38, 0x20002}, {0x3c, 0}, {0x40, 0}, {0x44, 0},
        {0x48, 0x01110080}, {0x4c, 6}, {0x50, 0}, {0x54, 0},
        {0x58, 0xff}, {0x5c, 0}, {0x60, 0xff}, {0x64, 0}, {0x68, 0},
        {0x6c, 0}, {0x70, 0}, {0x74, 0xff}, {0x78, 0}, {0x7c, 0xff},
        {0x80, 0}, {0x84, 0}, {0x88, 0}
    };
    if (index >= 3 || !r || !p || width != units[index].width ||
        height != units[index].height || r[0] || r[2] != 0x200087e0 ||
        r[3] != 0x88000 || r[5] ||
        z62_result_word(p, 4) != units[index].crop ||
        z62_result_word(p, 12) != 0x10003 + index ||
        z62_result_word(p, 0x2c) != (units[index].width - 1) << 16 ||
        z62_result_word(p, 0x30) != (units[index].rows - 1) << 16 ||
        z62_result_word(p, 0x34) != units[index].scale ||
        z62_result_word(p, 0x94) != r[2] || z62_result_word(p, 0x98) != r[3]) {
        return 0;
    }
    for (unsigned i = 0; i < sizeof(profile) / sizeof(profile[0]); i++) {
        if (z62_result_word(p, profile[i].offset) != profile[i].value) {
            return 0;
        }
    }
    return units[index].bit;
}
#endif
