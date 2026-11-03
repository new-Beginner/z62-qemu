/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <stdio.h>
#include <stdlib.h>
#include "nikon-z62-main-source.h"
#include "nikon-z62-capturework-pixels.h"
#define CHECK(x) do { if (!(x)) { fprintf(stderr,"line %d: %s\n",__LINE__,#x); return 1; } } while (0)

static void put32(uint8_t *p,uint32_t value)
{ for (unsigned i=0;i<4;i++) p[i]=(uint8_t)(value>>(8*i)); }
static void repair(uint8_t *packet)
{ put32(packet+88,z62_main_crc32(packet,88)); }

static int lifecycle(uint8_t *packet,size_t size)
{
    Z62MainMetadata meta; CHECK(z62_main_parse(packet,size,&meta)==Z62_MAIN_OK);
    uint8_t *memory=malloc(meta.bytes); CHECK(memory); Z62MainSource s;
    Z62MainLease first,second,third;
    CHECK(z62_main_source_init(&s,memory,meta.bytes));
    CHECK(z62_main_source_start(&s)==Z62_MAIN_STATE);
    CHECK(z62_main_source_publish(&s,packet,size)==Z62_MAIN_OK);
    CHECK(z62_main_source_begin(&s,&first)==Z62_MAIN_STATE);
    CHECK(z62_main_source_start(&s)==Z62_MAIN_OK);
    CHECK(z62_main_source_begin(&s,&first)==Z62_MAIN_OK);
    CHECK(z62_main_source_begin(&s,&second)==Z62_MAIN_BUSY);
    CHECK(z62_main_source_publish(&s,packet,size)==Z62_MAIN_BUSY);
    CHECK(!memcmp(memory,packet+96,meta.bytes));
    z62_main_source_cancel(&s);
    CHECK(z62_main_source_release(&s,&first)==Z62_MAIN_STALE);
    CHECK(z62_main_source_begin(&s,&second)==Z62_MAIN_OK && second.serial!=first.serial);
    z62_main_source_stop(&s);
    CHECK(z62_main_source_release(&s,&second)==Z62_MAIN_STALE);
    CHECK(z62_main_source_begin(&s,&third)==Z62_MAIN_STATE);
    CHECK(z62_main_source_start(&s)==Z62_MAIN_OK);
    CHECK(z62_main_source_begin(&s,&third)==Z62_MAIN_OK);
    CHECK(z62_main_source_release(&s,&first)==Z62_MAIN_STALE);
    CHECK(z62_main_source_release(&s,&third)==Z62_MAIN_OK);
    CHECK(z62_main_source_release(&s,&third)==Z62_MAIN_STALE);
    CHECK(z62_main_source_publish(&s,packet,size)==Z62_MAIN_SEQUENCE);
    put32(packet+40,2); repair(packet);
    CHECK(z62_main_source_publish(&s,packet,size)==Z62_MAIN_OK);
    CHECK(s.meta.publication==2);
    CHECK(z62_main_source_begin(&s,&first)==Z62_MAIN_OK);
    z62_main_source_reset(&s);
    CHECK(s.valid && s.meta.publication==2 && !s.running && !s.leased);
    CHECK(z62_main_source_release(&s,&first)==Z62_MAIN_STALE);
    CHECK(z62_main_source_start(&s)==Z62_MAIN_OK);
    s.serial=UINT64_MAX;
    CHECK(z62_main_source_begin(&s,&first)==Z62_MAIN_STATE);
    z62_main_source_stop(&s); CHECK(s.serial==UINT64_MAX && !s.running);
    CHECK(z62_main_source_start(&s)==Z62_MAIN_STATE);
    free(memory); return 0;
}

static int rejects(uint8_t *packet,size_t size)
{
    Z62MainMetadata meta; CHECK(z62_main_parse(packet,size,&meta)==Z62_MAIN_OK);
    uint8_t *memory=malloc(meta.bytes),*bad=malloc(size),*before=malloc(meta.bytes);
    CHECK(memory && bad && before); Z62MainSource s;
    CHECK(z62_main_source_init(&s,memory,meta.bytes));
    CHECK(z62_main_source_publish(&s,packet,size)==Z62_MAIN_OK);
    memcpy(before,memory,meta.bytes);
    const unsigned offsets[]={0,4,8,12,16,20,24,28,40,48,64,68,72,76,80,84,88,92,96};
    for (unsigned i=0;i<sizeof(offsets)/sizeof(offsets[0]);i++) {
        memcpy(bad,packet,size); bad[offsets[i]]^=1;
        CHECK(z62_main_source_publish(&s,bad,size)!=Z62_MAIN_OK);
        CHECK(!memcmp(before,memory,meta.bytes) && s.meta.publication==1 && !s.leased);
    }
    for (unsigned i=0;i<5;i++) {
        memcpy(bad,packet,size); put32(bad+40,2);
        if (i==0) put32(bad+64,2); /* correct CRC, wrong pixel domain */
        if (i==1) put32(bad+12,2); /* auxiliary role */
        if (i==2) put32(bad+32,63); /* changed epoch */
        if (i==3) put32(bad+56,0); /* time rewind */
        if (i==4) put32(bad+16,UINT32_MAX); /* extent overflow */
        repair(bad);
        CHECK(z62_main_source_publish(&s,bad,size)!=Z62_MAIN_OK);
        CHECK(!memcmp(before,memory,meta.bytes) && s.meta.publication==1);
    }
    CHECK(z62_main_source_publish(&s,packet,size-1)!=Z62_MAIN_OK);
    CHECK(z62_main_source_publish(&s,NULL,size)!=Z62_MAIN_OK);
    s.capacity=meta.bytes-1; memcpy(bad,packet,size); put32(bad+40,2); repair(bad);
    CHECK(z62_main_source_publish(&s,bad,size)==Z62_MAIN_CAPACITY);
    CHECK(!memcmp(before,memory,meta.bytes));
    free(memory); free(bad); free(before); return 0;
}

static int render(uint8_t *packet,size_t size,int argc,char **argv)
{
    CHECK(argc==11); Z62MainMetadata meta;
    CHECK(z62_main_parse(packet,size,&meta)==Z62_MAIN_OK);
    Z62CaptureWorkPixelsConfig c={0};
    c.input_width=meta.width; c.input_height=meta.height; c.input_stride=meta.stride;
    c.intermediate_width=(uint32_t)strtoul(argv[3],NULL,10);
    c.intermediate_height=(uint32_t)strtoul(argv[4],NULL,10);
    c.output_width=(uint32_t)strtoul(argv[5],NULL,10);
    c.output_height=(uint32_t)strtoul(argv[6],NULL,10);
    c.bits=(uint8_t)strtoul(argv[7],NULL,10); c.output_stride=(uint32_t)strtoul(argv[8],NULL,10);
    c.cfa=1; c.use_lut=1; uint16_t lut[256]; char *position=argv[9];
    for (unsigned i=0;i<256;i++) {
        char *end; unsigned long value=strtoul(position,&end,10);
        CHECK(end!=position && value<=65535 && (i==255?*end=='\0':*end==','));
        lut[i]=(uint16_t)value; position=end+1;
    }
    c.lookup=lut;
    uint64_t output_size=(uint64_t)c.output_stride*c.output_height;
    CHECK(output_size<=Z62_MAIN_MAX_BYTES && output_size<=SIZE_MAX);
    Z62CaptureWorkPixelsPlan plan;
    CHECK(z62_capturework_pixels_plan(&c,meta.bytes,(size_t)output_size,&plan)==Z62_CW_PIXELS_OK);
    uint8_t *memory=malloc(meta.bytes),*output=malloc((size_t)output_size);
    CHECK(memory && output); Z62MainSource s; Z62MainLease lease;
    CHECK(z62_main_source_init(&s,memory,meta.bytes));
    CHECK(z62_main_source_publish(&s,packet,size)==Z62_MAIN_OK);
    CHECK(z62_main_source_start(&s)==Z62_MAIN_OK);
    CHECK(z62_main_source_begin(&s,&lease)==Z62_MAIN_OK);
    memset(output,0xa5,(size_t)output_size);
    CHECK(z62_capturework_pixels_pack(&c,lease.pixels,lease.meta.bytes,output,(size_t)output_size)==Z62_CW_PIXELS_OK);
    CHECK(!memcmp(memory,packet+96,meta.bytes));
    FILE *file=fopen(argv[10],"wb"); CHECK(file);
    CHECK(fwrite(output,1,(size_t)output_size,file)==(size_t)output_size); CHECK(!fclose(file));
    CHECK(z62_main_source_release(&s,&lease)==Z62_MAIN_OK);
    z62_main_source_stop(&s);
    free(memory); free(output); return 0;
}

int main(int argc,char **argv)
{
    CHECK(argc>=3); FILE *file=fopen(argv[2],"rb"); CHECK(file);
    CHECK(!fseek(file,0,SEEK_END)); long length=ftell(file);
    CHECK(length>=96 && (uint64_t)length<=Z62_MAIN_MAX_BYTES+96);
    CHECK(!fseek(file,0,SEEK_SET)); uint8_t *packet=malloc((size_t)length); CHECK(packet);
    CHECK(fread(packet,1,(size_t)length,file)==(size_t)length); CHECK(!fclose(file));
    Z62MainMetadata meta; CHECK(z62_main_parse(packet,(size_t)length,&meta)==Z62_MAIN_OK);
    int result=1;
    if (!strcmp(argv[1],"parse")) {
        CHECK(z62_main_u32(packet+96)==(65520u|UINT32_C(14946)<<16));
        result=0;
    } else if (!strcmp(argv[1],"lifecycle")) result=lifecycle(packet,(size_t)length);
    else if (!strcmp(argv[1],"rejects")) result=rejects(packet,(size_t)length);
    else if (!strcmp(argv[1],"render")) result=render(packet,(size_t)length,argc,argv);
    if (!result) printf("{\"completed\":true,\"width\":%u,\"height\":%u,\"stride\":%u,\"publish_id\":%llu,\"frame_id\":%llu}\n",
        meta.width,meta.height,meta.stride,(unsigned long long)meta.publication,(unsigned long long)meta.frame);
    free(packet); return result;
}
