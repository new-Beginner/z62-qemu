#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "../../qemu/z62-grid/nikon-z62-grid-pixels.h"

static void fill(uint8_t *p, uint16_t value)
{
    for (unsigned i = 0; i < 5120; i += 2) {
        p[i] = value;
        p[i+1] = value >> 8;
    }
}

int main(void)
{
    uint8_t input[3][5120], before[3][5120], output[3840+32];
    fill(input[0], 0x100); fill(input[1], 0x200); fill(input[2], 0x300);
    memcpy(before,input,sizeof(input));
    memset(output,0xa5,sizeof(output));
    assert(z62_grid_convert(input[0],input[1],input[2],5120,output+16,3840));
    assert(memcmp(input,before,sizeof(input)) == 0);
    for (unsigned y = 0; y < 40; y++) {
        for (unsigned x = 0; x < 90; x += 3) {
            assert(output[16+y*96+x] == 0);
            assert(output[16+y*96+x+1] == 2);
            assert(output[16+y*96+x+2] == 0x20);
        }
        for (unsigned x = 90; x < 96; x++) assert(output[16+y*96+x] == 0);
    }
    for (unsigned x = 0; x < 16; x++) assert(output[x] == 0xa5 && output[3856+x] == 0xa5);
    memset(input,0,sizeof(input));
    input[0][0] = 0xff; input[0][1] = 0x0f;
    input[1][2] = input[2][2] = 0xff; input[1][3] = input[2][3] = 0x0f;
    assert(z62_grid_convert(input[0],input[1],input[2],5120,output+16,3840));
    assert(output[16] == 0x55 && output[17] == 0xa5 && output[18] == 0xaa);
    memset(output,0xa5,sizeof(output));
    input[2][39*128+59*2+1] = 0x10;
    assert(!z62_grid_convert(input[0],input[1],input[2],5120,output+16,3840));
    for (unsigned i = 0; i < sizeof(output); i++) assert(output[i] == 0xa5);
    assert(!z62_grid_convert(input[0],input[1],input[2],5119,output+16,3840));
    assert(!z62_grid_convert(input[0],input[1],input[2],5120,output+16,3839));
    assert(!z62_grid_convert(input[0],input[1],input[2],5120,input[0],3840));
    puts("Three real LE-u16 inputs -> rounded RGB mean -> packed12; sources, padding, guards and failure atomicity passed");
    return 0;
}
