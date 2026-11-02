#include "nikon-z62-preview-results-profile.h"
#define main initial_profile_tests
#include "z62_preview_results_profile_test.c"
#undef main

int main(void)
{
    assert(initial_profile_tests() == 0);
    uint32_t r[6];
    uint8_t p[160];
    for (unsigned u = 0; u < 3; u++) {
        fixture(u, r, p);
        put(p, 0x1c, 0xff010200);
        const unsigned w[3] = {1920, 1024, 1024};
        const unsigned h[3] = {1080, 682, 680};
        const uint32_t bits[3] = {0x20, 0, 0x40};
        assert(z62_preview_result_mask(u, w[u], h[u], r, p) == bits[u]);
        put(p, 0x1c, 0xff010400);
        assert(z62_preview_result_mask(u, w[u], h[u], r, p) == 0);
    }
    puts("Observed Z62 per-unit format transitions accepted; unobserved formats rejected");
    return 0;
}
