/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <assert.h>
#include <stdio.h>
#include "nikon-z62-preview-results-profile.h"
#include "../../qemu/z62-photo-results/nikon-z62-photo-results-profile.h"

static void put(uint8_t *p,unsigned offset,uint32_t value)
{
    p[offset]=value; p[offset+1]=value>>8;
    p[offset+2]=value>>16; p[offset+3]=value>>24;
}

int main(void)
{
    /* Original post-return unit49 words captured at44.810 guest seconds. */
    const uint32_t actual[40]={
        0x110a0000,0x70000,0,0x10004,0,0,0,0xff010000,0,0,
        0x11080040,0x3ff0000,0x2b90000,0x1000100,0x20002,0,0,0,
        0x1110080,6,0,0,0xff,0,0xff,0,0,0,0,0xff,0,0xff,0,0,0,
        0x103b7541,2,0x200087e0,0x88000,0};
    uint32_t registers[6]={0,0,0x200087e0,0x88000,0,0};
    uint8_t payload[160], original[160];
    for(unsigned i=0;i<40;i++) { put(payload,i*4,actual[i]); }
    memcpy(original,payload,sizeof(payload));
    assert(z62_preview_result_mask(1,1024,680,registers,payload)==0);
    assert(z62_photo_result_mask(1,1024,680,registers,payload)==1);
    assert(!memcmp(payload,original,sizeof(payload)));
    puts("PASS captured680/698 layout, original payload unchanged");
    for(unsigned offset=0;offset<160;offset+=4) {
        if(offset==0x8c || offset==0x90 || offset==0x9c) { continue; }
        uint8_t changed[160]; memcpy(changed,payload,sizeof(changed));
        put(changed,offset,z62_result_word(changed,offset)^1);
        assert(z62_photo_result_mask(1,1024,680,registers,changed)==0);
    }
    puts("PASS independent opaque fields still qualified");
    assert(z62_photo_result_mask(0,1024,680,registers,payload)==0);
    assert(z62_photo_result_mask(1,1024,576,registers,payload)==0);
    assert(z62_photo_result_mask(1,1024,682,registers,payload)==0);
    assert(z62_photo_result_mask(1,1024,680,NULL,payload)==0);
    puts("PASS wrong route, movie layout and missing registers rejected");
    put(payload,0x30,699u<<16);
    assert(z62_preview_result_mask(1,1024,682,registers,payload)==1);
    puts("PASS old682/700 matcher remains available");
    return 0;
}
