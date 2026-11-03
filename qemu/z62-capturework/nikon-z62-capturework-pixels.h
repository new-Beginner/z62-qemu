/* SPDX-License-Identifier: GPL-2.0-or-later
 * Finite software capture pixel operator. No MMIO, DMA, timers or completion.
 * Two-stage nearest sampling, CFA tile selection and LUT arithmetic are explicit
 * functional conventions. Inspired by nightglasses/z7ii-qemu capturework, with
 * rational stage composition for the independently observed Z62 dimensions.
 * This is not physical ISP arithmetic or a source of real PDAF measurements.
 */
#ifndef NIKON_Z62_CAPTUREWORK_PIXELS_H
#define NIKON_Z62_CAPTUREWORK_PIXELS_H

#include <stddef.h>
#include <stdint.h>
#include <string.h>

#define Z62_CW_MAX_SAMPLES (UINT64_C(4) * 1024 * 1024)
#define Z62_CW_MAX_BYTES (UINT64_C(64) * 1024 * 1024)

typedef enum Z62CaptureWorkPixelsResult {
    Z62_CW_PIXELS_OK,
    Z62_CW_PIXELS_CONFIG,
    Z62_CW_PIXELS_GEOMETRY,
    Z62_CW_PIXELS_STRIDE,
    Z62_CW_PIXELS_SPAN,
    Z62_CW_PIXELS_LUT,
    Z62_CW_PIXELS_OVERLAP
} Z62CaptureWorkPixelsResult;

typedef struct Z62CaptureWorkPixelsConfig {
    uint32_t input_width, input_height, input_stride;
    uint32_t intermediate_width, intermediate_height;
    uint32_t output_width, output_height, output_stride;
    uint32_t correction_flags;
    uint8_t bits, cfa, use_lut;
    const uint16_t *lookup;
} Z62CaptureWorkPixelsConfig;

typedef struct Z62CaptureWorkPixelsPlan {
    size_t input_span, output_span, output_row_bytes;
} Z62CaptureWorkPixelsPlan;

static inline Z62CaptureWorkPixelsResult z62_capturework_pixels_plan(
    const Z62CaptureWorkPixelsConfig *c, size_t source_size,
    size_t destination_size, Z62CaptureWorkPixelsPlan *plan)
{
    uint64_t source_span, destination_span, row_bits, row_bytes;
    if (!c || !plan || c->correction_flags || c->cfa > 1 || c->use_lut > 1 ||
        (c->bits != 12 && c->bits != 14 && c->bits != 16)) {
        return Z62_CW_PIXELS_CONFIG;
    }
    if (!c->input_width || !c->input_height || !c->intermediate_width ||
        !c->intermediate_height || !c->output_width || !c->output_height ||
        c->input_width > 4096 || c->input_height > 4096 ||
        (uint64_t)c->input_width * c->input_height > Z62_CW_MAX_SAMPLES ||
        c->intermediate_width > c->input_width || c->intermediate_height > c->input_height ||
        c->output_width > c->intermediate_width || c->output_height > c->intermediate_height ||
        (c->cfa && ((c->input_width | c->input_height | c->intermediate_width |
                    c->intermediate_height | c->output_width | c->output_height) & 1u))) {
        return Z62_CW_PIXELS_GEOMETRY;
    }
    row_bits = (uint64_t)c->output_width * c->bits;
    if (row_bits & 7u) {
        return Z62_CW_PIXELS_GEOMETRY;
    }
    row_bytes = row_bits / 8;
    if ((uint64_t)c->input_stride < 2 * (uint64_t)c->input_width ||
        (uint64_t)c->output_stride < row_bytes) {
        return Z62_CW_PIXELS_STRIDE;
    }
    source_span = (uint64_t)c->input_stride * c->input_height;
    destination_span = (uint64_t)c->output_stride * c->output_height;
    if (source_span > Z62_CW_MAX_BYTES || destination_span > Z62_CW_MAX_BYTES ||
        source_span > SIZE_MAX || destination_span > SIZE_MAX ||
        source_span > source_size || destination_span > destination_size) {
        return Z62_CW_PIXELS_SPAN;
    }
    if (c->use_lut) {
        if (!c->lookup) {
            return Z62_CW_PIXELS_LUT;
        }
        for (unsigned i = 0; i < 256; i++) {
            uint32_t value = c->lookup[i];
            if (value >= (UINT32_C(1) << c->bits) ||
                (i && value <= c->lookup[i - 1])) {
                return Z62_CW_PIXELS_LUT;
            }
        }
    }
    *plan = (Z62CaptureWorkPixelsPlan) {
        .input_span = (size_t)source_span,
        .output_span = (size_t)destination_span,
        .output_row_bytes = (size_t)row_bytes
    };
    return Z62_CW_PIXELS_OK;
}

static inline uint32_t z62_capturework_coordinate(uint32_t x, uint32_t input,
    uint32_t intermediate, uint32_t output, uint8_t cfa)
{
    uint32_t phase = cfa ? x & 1u : 0;
    uint32_t tile = cfa ? 2u : 1u;
    uint64_t middle = (uint64_t)(x / tile) * (intermediate / tile) / (output / tile);
    uint64_t source = middle * (input / tile) / (intermediate / tile);
    return (uint32_t)(source * tile + phase);
}

static inline Z62CaptureWorkPixelsResult z62_capturework_pixels_pack(
    const Z62CaptureWorkPixelsConfig *config, const uint8_t *source,
    size_t source_size, uint8_t *destination, size_t destination_size)
{
    Z62CaptureWorkPixelsConfig c;
    Z62CaptureWorkPixelsPlan plan;
    Z62CaptureWorkPixelsResult result;
    uint16_t private_lookup[256];
    uintptr_t source_address = (uintptr_t)source;
    uintptr_t destination_address = (uintptr_t)destination;
    if (!config || !source || !destination) {
        return Z62_CW_PIXELS_CONFIG;
    }
    c = *config;
    /* Freeze the lookup input before validation or any destination mutation. */
    if (c.use_lut == 1 && c.lookup) {
        memcpy(private_lookup, c.lookup, sizeof(private_lookup));
        c.lookup = private_lookup;
    }
    result = z62_capturework_pixels_plan(&c, source_size, destination_size, &plan);
    if (result != Z62_CW_PIXELS_OK) {
        return result;
    }
    if (plan.input_span > UINTPTR_MAX - source_address ||
        plan.output_span > UINTPTR_MAX - destination_address ||
        (source_address < destination_address + plan.output_span &&
         destination_address < source_address + plan.input_span)) {
        return Z62_CW_PIXELS_OVERLAP;
    }
    for (uint32_t y = 0; y < c.output_height; y++) {
        uint32_t sy = z62_capturework_coordinate(y, c.input_height,
            c.intermediate_height, c.output_height, c.cfa);
        const uint8_t *input_row = source + (size_t)sy * c.input_stride;
        uint8_t *output_row = destination + (size_t)y * c.output_stride;
        uint32_t accumulator = 0;
        unsigned available = 0;
        size_t column = 0;
        for (uint32_t x = 0; x < c.output_width; x++) {
            uint32_t sx = z62_capturework_coordinate(x, c.input_width,
                c.intermediate_width, c.output_width, c.cfa);
            uint32_t sample = (uint32_t)input_row[2 * sx] |
                              (uint32_t)input_row[2 * sx + 1] << 8;
            uint32_t value = c.use_lut ? c.lookup[sample >> 8] : sample >> (16 - c.bits);
            accumulator |= value << available;
            available += c.bits;
            while (available >= 8) {
                output_row[column++] = (uint8_t)accumulator;
                accumulator >>= 8;
                available -= 8;
            }
        }
        /* Preflight guaranteed whole bytes. Row padding is deliberately untouched. */
    }
    return Z62_CW_PIXELS_OK;
}

#endif
