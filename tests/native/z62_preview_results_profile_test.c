#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "../../qemu/z62-preview-results/nikon-z62-preview-results-profile.h"

static void put(uint8_t *p, unsigned offset, uint32_t v)
{
    for (unsigned i = 0; i < 4; i++) {
        p[offset + i] = v >> (8 * i);
    }
}

static void fixture(unsigned unit, uint32_t *r, uint8_t *p)
{
    const uint32_t words[40] = {
        0x110a0000, 0x400000, 0, 0x10003, 0, 0, 0, 0xff010000, 0, 0,
        0x11080040, 0x077f0000, 0x04530000, 0x1000100, 0x20002, 0, 0, 0,
        0x01110080, 6, 0, 0, 0xff, 0, 0xff, 0, 0, 0, 0, 0xff, 0, 0xff,
        0, 0, 0, 0xdeadbeef, 0xf00dbabe, 0x200087e0, 0x88000, 0
    };
    for (unsigned i = 0; i < 40; i++) {
        put(p, i * 4, words[i]);
    }
    const uint32_t registers[6] = {0, 3, 0x200087e0, 0x88000, 0xc2200000, 0};
    memcpy(r, registers, sizeof(registers));
    if (unit == 1) {
        put(p, 4, 0x70000);
        put(p, 12, 0x10004);
        put(p, 0x2c, 0x03ff0000);
        put(p, 0x30, 0x02bb0000);
    } else if (unit == 2) {
        put(p, 4, 0x460000);
        put(p, 12, 0x10005);
        put(p, 0x2c, 0x03ff0000);
        put(p, 0x30, 0x02b90000);
        put(p, 0x34, 0x400040);
    }
}

int main(void)
{
    const unsigned widths[3] = {1920, 1024, 1024};
    const unsigned heights[3] = {1080, 682, 680};
    const uint32_t expected[3] = {0x20, 1, 0x40};
    uint32_t r[6];
    uint8_t p[160], before[160];
    for (unsigned u = 0; u < 3; u++) {
        fixture(u, r, p);
        memcpy(before, p, sizeof(p));
        assert(z62_preview_result_mask(u, widths[u], heights[u], r, p) == expected[u]);
        assert(memcmp(before, p, sizeof(p)) == 0);
        put(p, 0x8c, 0);
        put(p, 0x90, 0xffffffff);
        assert(z62_preview_result_mask(u, widths[u], heights[u], r, p) == expected[u]);
        assert(z62_preview_result_mask(u, widths[u], heights[u] - 2, r, p) == 0);
        put(p, 0x30, 0x02cb0000); /* Z72 internal height is not the Z62 recipe. */
        assert(z62_preview_result_mask(u, widths[u], heights[u], r, p) == 0);
    }
    const unsigned changed[] = {0, 4, 8, 12, 0x1c, 0x28, 0x2c, 0x34, 0x38,
                                0x48, 0x4c, 0x58, 0x94, 0x98};
    for (unsigned i = 0; i < sizeof(changed) / sizeof(changed[0]); i++) {
        fixture(0, r, p);
        p[changed[i]] ^= 1;
        assert(z62_preview_result_mask(0, 1920, 1080, r, p) == 0);
    }
    for (unsigned i = 0; i < 6; i++) {
        if (i == 1 || i == 4) {
            continue; /* Status and pointer are handled outside this pure validator. */
        }
        fixture(0, r, p);
        r[i] ^= 1;
        assert(z62_preview_result_mask(0, 1920, 1080, r, p) == 0);
    }
    assert(z62_preview_result_mask(3, 1920, 1080, r, p) == 0);
    puts("Z62 physical output profiles, independent result bits, metadata independence and rejection checks passed");
    return 0;
}
