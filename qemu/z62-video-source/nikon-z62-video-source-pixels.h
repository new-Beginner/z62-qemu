/* SPDX-License-Identifier: GPL-2.0-or-later
 * Explicit C-level crop/pad view; not a recovered Nikon sensor/ISP operator.
 */
#ifndef NIKON_Z62_VIDEO_SOURCE_PIXELS_H
#define NIKON_Z62_VIDEO_SOURCE_PIXELS_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

static inline bool z62_video_raw_view(const uint8_t *source, size_t source_bytes,
    unsigned source_width, unsigned source_height, size_t source_stride,
    uint8_t *output, size_t output_bytes, unsigned width, unsigned height,
    size_t output_stride, int origin_x, int origin_y)
{
    size_t source_active=(size_t)source_width/2*3, active=(size_t)width/2*3;
    if (!source || !output || source_width < 2 || source_height < 2 ||
        width < 2 || height < 2 || source_width > 4096 || source_height > 4096 ||
        width > 4096 || height > 4096 || ((source_width|source_height|width|height)&1) ||
        origin_x < -4096 || origin_x > 4096 || origin_y < -4096 || origin_y > 4096 ||
        origin_x%2 || origin_y%2 || source_stride < source_active ||
        output_stride < active || source_stride > 65536 || output_stride > 65536 ||
        source_stride > SIZE_MAX/source_height || output_stride > SIZE_MAX/height) {
        return false;
    }
    size_t source_span=(source_height-1)*source_stride+source_active;
    size_t output_span=(height-1)*output_stride+active;
    uintptr_t input_address=(uintptr_t)source, output_address=(uintptr_t)output;
    if (source_bytes < source_span || output_bytes < output_span ||
        input_address > UINTPTR_MAX-source_span || output_address > UINTPTR_MAX-output_span ||
        (input_address < output_address+output_span && output_address < input_address+source_span)) {
        return false;
    }
    /* Caller owns the ROI choice and memory backing. Odd origins would change
     * CFA phase and need a different conversion, so they are never rounded.
     * Every admission check finishes before the first active-byte write. */
    for (unsigned y=0; y<height; y++) {
        int input_y=origin_y+(int)y;
        unsigned sy=input_y < 0 ? (y&1) :
            input_y >= (int)source_height ? source_height-2+(y&1) : (unsigned)input_y;
        for (unsigned x=0; x<width; x+=2) {
            int input_x=origin_x+(int)x;
            unsigned sx=input_x < 0 ? 0 :
                input_x >= (int)source_width ? source_width-2 : (unsigned)input_x;
            /* One packed12 pair is one complete same-row CFA cell. Clamp a
             * whole cell, preserving the two colors rather than duplicating
             * the last scalar pixel into its opposite-color neighbour. */
            memcpy(output+(size_t)y*output_stride+x/2*3,
                   source+(size_t)sy*source_stride+sx/2*3,3);
        }
    }
    return true;
}
#endif
