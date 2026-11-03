/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <assert.h>
#include <stdio.h>
#include "../../qemu/z62-mode-geometry/nikon-z62-mode-grid-pixels.h"
#include "../../qemu/z62-grid/nikon-z62-grid-pixels.h"

static uint8_t inputs[3][128*40], output[96*40+16], legacy[96*40];

static void prepare(unsigned height)
{
    memset(inputs, 0xff, sizeof(inputs));
    memset(output, 0xa5, sizeof(output));
    for (unsigned y=0; y<height; y++) {
        for (unsigned x=0; x<60; x++) {
            unsigned value[3]={y*31+x, (y+17)*5+x, 2000-x};
            for (unsigned c=0; c<3; c++) {
                inputs[c][y*128+x*2]=value[c];
                inputs[c][y*128+x*2+1]=value[c]>>8;
            }
        }
    }
}

int main(void)
{
    const uint8_t *planes[3]={inputs[0],inputs[1],inputs[2]};
    size_t available[3]={sizeof(inputs[0]),sizeof(inputs[1]),sizeof(inputs[2])};
    size_t row[3]={128,128,128};
    prepare(34);
    /* Rows34..39 are invalid active samples; a fixed40-row read must fail. */
    assert(z62_mode_grid_convert(planes,available,60,34,row,output,sizeof(output),96));
    assert(output[0]==0xb7 && output[1]==0x72 && output[2]==0x2b);
    for (unsigned y=0;y<34;y++) {
        for (unsigned x=90;x<96;x++) { assert(output[y*96+x]==0); }
    }
    for (unsigned i=34*96;i<sizeof(output);i++) { assert(output[i]==0xa5); }
    puts("PASS variable34, exact packed vector, row padding and untouched tail");

    prepare(40);
    assert(z62_grid_convert(inputs[0],inputs[1],inputs[2],sizeof(inputs[0]),legacy,sizeof(legacy)));
    assert(z62_mode_grid_convert(planes,available,60,40,row,output,sizeof(output),96));
    assert(!memcmp(output,legacy,sizeof(legacy)));
    puts("PASS photo40 byte-exact legacy compatibility");

    prepare(34);
    inputs[2][33*128+59*2]=0;
    inputs[2][33*128+59*2+1]=0x10;
    assert(!z62_mode_grid_convert(planes,available,60,34,row,output,sizeof(output),96));
    for (unsigned i=0;i<sizeof(output);i++) { assert(output[i]==0xa5); }
    puts("PASS late invalid source performs no output writes");

    prepare(34);
    assert(!z62_mode_grid_convert(planes,available,59,34,row,output,sizeof(output),96));
    assert(!z62_mode_grid_convert(planes,available,60,34,row,output,34*96-1,96));
    assert(!z62_mode_grid_convert(planes,available,60,34,row,inputs[0],sizeof(inputs[0]),96));
    available[2]=128*34-1;
    assert(!z62_mode_grid_convert(planes,available,60,34,row,output,sizeof(output),96));
    for (unsigned i=0;i<sizeof(output);i++) { assert(output[i]==0xa5); }
    puts("PASS dimensions, extent, alias and short-input guards");
    return 0;
}
