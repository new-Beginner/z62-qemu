#include <assert.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include "../../qemu/z62-continuous-stats/nikon-z62-statistics-pixels.h"

static unsigned get16(const uint8_t *p) { return p[0] | (unsigned)p[1] << 8; }
static uint32_t get32(const uint8_t *p)
{ return p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24; }
static void pair(uint8_t *p, unsigned a, unsigned b)
{ p[0] = a; p[1] = (a >> 8) | (b & 15) << 4; p[2] = b >> 4; }
static void fill(uint8_t *raw, unsigned r, unsigned g1, unsigned g2, unsigned b)
{
    memset(raw, 0, Z62_STATS_RAW_BYTES);
    for (unsigned y = 0; y < Z62_STATS_RAW_H; y += 2) {
        for (unsigned x = 0; x < Z62_STATS_RAW_W; x += 2) {
            pair(raw + y*Z62_STATS_RAW_STRIDE + x/2*3, r, g1);
            pair(raw + (y+1)*Z62_STATS_RAW_STRIDE + x/2*3, g2, b);
        }
    }
}

int main(void)
{
    uint8_t *allocation = malloc(Z62_STATS_RAW_BYTES + 32);
    uint8_t *snapshot = malloc(Z62_STATS_RAW_BYTES);
    struct { uint8_t before[16]; Z62StatisticsPixels pixels; uint8_t after[16]; } *out = malloc(sizeof(*out));
    assert(allocation && snapshot && out);
    memset(allocation, 0xa5, Z62_STATS_RAW_BYTES + 32);
    memset(out, 0xa5, sizeof(*out));
    uint8_t *raw = allocation + 16;
    fill(raw, 400, 800, 1200, 1600);
    memcpy(snapshot, raw, Z62_STATS_RAW_BYTES);
    assert(z62_statistics_calculate(raw, Z62_STATS_RAW_BYTES, &out->pixels));
    assert(memcmp(raw, snapshot, Z62_STATS_RAW_BYTES) == 0);
    uint64_t samples = 0;
    for (unsigned y = 0; y < 20; y++) {
        for (unsigned x = 0; x < 30; x++) {
            const uint8_t *p = out->pixels.sums + y*480 + x*16;
            uint32_t n = get32(p+12);
            assert(n > 0 && get32(p) == 400*n && get32(p+4) == 1000*n && get32(p+8) == 1600*n);
            assert(get16(out->pixels.scalar + y*64 + x*2) == 1000);
            samples += n;
        }
        for (unsigned x = 60; x < 64; x++) { assert(out->pixels.scalar[y*64+x] == 0); }
    }
    assert(samples == 380771);
    for (unsigned y = 0; y < 40; y++) {
        for (unsigned x = 0; x < 60; x++) {
            assert(get16(out->pixels.rgb[0] + y*128+x*2) == 400);
            assert(get16(out->pixels.rgb[1] + y*128+x*2) == 1000);
            assert(get16(out->pixels.rgb[2] + y*128+x*2) == 1600);
        }
        for (unsigned c = 0; c < 3; c++) {
            for (unsigned x = 120; x < 128; x++) { assert(out->pixels.rgb[c][y*128+x] == 0); }
        }
    }
    fill(raw, 0, 0, 0, 0);
    pair(raw, 4095, 0);
    pair(raw + 1005*2272 + 756*3, 0, 4095);
    assert(z62_statistics_calculate(raw, Z62_STATS_RAW_BYTES, &out->pixels));
    assert(get32(out->pixels.sums) == 4095 && get32(out->pixels.sums+12) == 625);
    assert(get32(out->pixels.sums+19*480+29*16+8) == 4095);
    assert(get32(out->pixels.sums+19*480+29*16+12) == 676);
    assert(get16(out->pixels.scalar) == 2 && get16(out->pixels.scalar+19*64+58) == 2);
    assert(get16(out->pixels.rgb[0]) == 28);
    assert(get16(out->pixels.rgb[2]+39*128+118) == 24);
    assert(get16(out->pixels.rgb[0]+2) == 0 && get16(out->pixels.rgb[1]) == 0);
    fill(raw, 4095, 4095, 4095, 4095);
    assert(z62_statistics_calculate(raw, Z62_STATS_RAW_BYTES, &out->pixels));
    assert(get16(out->pixels.rgb[2]+39*128+118) == 4095 && get16(out->pixels.scalar) == 4095);
    Z62StatisticsPixels saved = out->pixels;
    assert(!z62_statistics_calculate(raw, Z62_STATS_RAW_BYTES-1, &out->pixels));
    assert(memcmp(&saved, &out->pixels, sizeof(saved)) == 0);
    assert(!z62_statistics_calculate(NULL, Z62_STATS_RAW_BYTES, &out->pixels));
    assert(!z62_statistics_calculate(raw, Z62_STATS_RAW_BYTES, NULL));
    memcpy(snapshot, raw, Z62_STATS_RAW_BYTES);
    assert(!z62_statistics_calculate(raw, Z62_STATS_RAW_BYTES, (Z62StatisticsPixels *)raw));
    assert(memcmp(raw, snapshot, Z62_STATS_RAW_BYTES) == 0);
    for (unsigned i = 0; i < 16; i++) {
        assert(allocation[i] == 0xa5 && allocation[Z62_STATS_RAW_BYTES+16+i] == 0xa5);
        assert(out->before[i] == 0xa5 && out->after[i] == 0xa5);
    }
    free(snapshot); free(allocation); free(out);
    puts("PASS: CFA colors, all cells, sum/count coverage, scalar mean, impulses, padding, bounds, immutable input");
    return 0;
}
