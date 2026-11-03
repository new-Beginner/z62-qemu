/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <stdio.h>
#include <stdlib.h>
#include "nikon-z62-raw-transfer.h"
#include "nikon-z62-capturework-pixels.h"
#include "nikon-z62-main-source.h"
#define CHECK(x) do { if (!(x)) { fprintf(stderr,"line %d: %s\n",__LINE__,#x); return 1; } } while (0)
static unsigned get16(const uint8_t *p) { return (unsigned)p[0]|(unsigned)p[1]<<8; }
static void put16(uint8_t *p,unsigned value) { p[0]=(uint8_t)value; p[1]=(uint8_t)(value>>8); }
static void put_code(uint8_t *p,unsigned x,unsigned bits,unsigned value)
{
    for (unsigned bit=0;bit<bits;bit++) {
        unsigned position=x*bits+bit;
        p[position/8]=(uint8_t)((p[position/8]&~(1u<<(position%8)))|(((value>>bit)&1u)<<(position%8)));
    }
}

static int roundtrip(const Z62RawTransfer *transfer)
{
    const unsigned width=256,height=256,in_stride=512;
    unsigned packed_stride=width*transfer->bits/8+4,decoded_stride=518;
    uint8_t *source=malloc(in_stride*height),*packed=malloc(packed_stride*height),*decoded=malloc(decoded_stride*height);
    CHECK(source && packed && decoded);
    for (unsigned i=0;i<65536;i++) put16(source+2*i,i);
    memset(packed,0xa5,packed_stride*height); memset(decoded,0xa5,decoded_stride*height);
    Z62CaptureWorkPixelsConfig c={0}; c.input_width=c.intermediate_width=c.output_width=width;
    c.input_height=c.intermediate_height=c.output_height=height;
    c.input_stride=in_stride; c.output_stride=packed_stride; c.bits=(uint8_t)transfer->bits;
    c.use_lut=(uint8_t)transfer->codec; c.lookup=transfer->lookup;
    CHECK(z62_capturework_pixels_pack(&c,source,in_stride*height,packed,packed_stride*height)==Z62_CW_PIXELS_OK);
    CHECK(z62_transfer_unpack(transfer,packed,packed_stride*height,width,height,packed_stride,
        decoded,decoded_stride*height,decoded_stride)==Z62_TRANSFER_OK);
    unsigned quantum=transfer->codec?256u:1u<<(16-transfer->bits);
    for (unsigned y=0;y<height;y++) {
        for (unsigned x=0;x<width;x++) {
            unsigned value=y*width+x,expected=value/quantum*quantum+quantum/2;
            CHECK(get16(decoded+(size_t)y*decoded_stride+2*x)==expected);
            Z62RawInterval interval; unsigned code=transfer->codec?transfer->lookup[value>>8]:value>>(16-transfer->bits);
            CHECK(z62_transfer_interval(transfer,code,&interval)==Z62_TRANSFER_OK);
            CHECK(interval.lower<=value && interval.upper>=value && interval.representative==expected);
        }
        for (unsigned x=width*2;x<decoded_stride;x++) CHECK(decoded[y*decoded_stride+x]==0xa5);
        for (unsigned x=width*transfer->bits/8;x<packed_stride;x++) CHECK(packed[y*packed_stride+x]==0xa5);
    }
    free(source); free(packed); free(decoded); return 0;
}

static int rejects(const Z62RawTransfer *transfer,const uint8_t *blob)
{
    CHECK(transfer->codec==1); uint16_t lut[256]; memcpy(lut,transfer->lookup,sizeof(lut));
    Z62RawTransfer frozen,before;
    CHECK(z62_transfer_snapshot(&frozen,12,1,lut)==Z62_TRANSFER_OK);
    before=frozen; lut[10]=65535; CHECK(frozen.lookup[10]==transfer->lookup[10]);
    CHECK(z62_transfer_snapshot(&frozen,12,1,lut)==Z62_TRANSFER_CONFIG);
    CHECK(!memcmp(&frozen,&before,sizeof(frozen)));
    uint8_t invalid[532]; memcpy(invalid,blob,532); invalid[528]^=1;
    CHECK(z62_transfer_load(&frozen,invalid,532)==Z62_TRANSFER_CONFIG);
    CHECK(!memcmp(&frozen,&before,sizeof(frozen)));
    uint8_t source[32]={0},output[32];
    for (unsigned i=0;i<4;i++) put_code(source,i,12,i==3?4095:transfer->lookup[i]);
    memset(output,0xa5,sizeof(output));
    CHECK(z62_transfer_unpack(transfer,source,8,4,1,8,output,sizeof(output),12)==Z62_TRANSFER_CODE);
    for (unsigned i=0;i<sizeof(output);i++) CHECK(output[i]==0xa5);
    put_code(source,3,12,transfer->lookup[3]); uint8_t old[32]; memcpy(old,source,sizeof(old));
    CHECK(z62_transfer_unpack(transfer,source,8,4,1,8,source+1,31,12)==Z62_TRANSFER_OVERLAP);
    CHECK(!memcmp(old,source,sizeof(old)));
    CHECK(z62_transfer_unpack(transfer,source,7,4,1,8,output,sizeof(output),12)==Z62_TRANSFER_SPAN);
    CHECK(z62_transfer_unpack(transfer,source,8,4,1,5,output,sizeof(output),12)==Z62_TRANSFER_GEOMETRY);
    CHECK(z62_transfer_unpack(transfer,source,8,4,1,8,output,11,12)==Z62_TRANSFER_SPAN);
    for (unsigned i=0;i<sizeof(output);i++) CHECK(output[i]==0xa5);
    return 0;
}

static int scene(const Z62RawTransfer *transfer,int argc,char **argv)
{
    CHECK(argc==11); FILE *file=fopen(argv[3],"rb"); CHECK(file);
    CHECK(!fseek(file,0,SEEK_END)); long length=ftell(file);
    CHECK(length>=96 && (uint64_t)length<=Z62_MAIN_MAX_BYTES+96);
    CHECK(!fseek(file,0,SEEK_SET)); uint8_t *packet=malloc((size_t)length); CHECK(packet);
    CHECK(fread(packet,1,(size_t)length,file)==(size_t)length); CHECK(!fclose(file));
    Z62MainMetadata meta; CHECK(z62_main_parse(packet,(size_t)length,&meta)==Z62_MAIN_OK);
    const Z62RawTransfer frozen=*transfer;
    Z62CaptureWorkPixelsConfig c={0};
    c.input_width=meta.width; c.input_height=meta.height; c.input_stride=meta.stride;
    c.intermediate_width=(uint32_t)strtoul(argv[4],NULL,10);
    c.intermediate_height=(uint32_t)strtoul(argv[5],NULL,10);
    c.output_width=(uint32_t)strtoul(argv[6],NULL,10); c.output_height=(uint32_t)strtoul(argv[7],NULL,10);
    c.output_stride=(uint32_t)strtoul(argv[8],NULL,10);
    c.cfa=1; c.bits=(uint8_t)frozen.bits; c.use_lut=(uint8_t)frozen.codec; c.lookup=frozen.lookup;
    uint64_t packed_bytes=(uint64_t)c.output_stride*c.output_height;
    CHECK(packed_bytes<=Z62_TRANSFER_MAX_BYTES && packed_bytes<=SIZE_MAX);
    Z62CaptureWorkPixelsPlan plan;
    CHECK(z62_capturework_pixels_plan(&c,meta.bytes,(size_t)packed_bytes,&plan)==Z62_CW_PIXELS_OK);
    uint32_t linear_stride=2*c.output_width+4;
    size_t linear_bytes=(size_t)linear_stride*c.output_height;
    uint8_t *memory=malloc(meta.bytes),*packed=malloc((size_t)packed_bytes),*linear=malloc(linear_bytes);
    CHECK(memory && packed && linear); Z62MainSource source; Z62MainLease lease;
    CHECK(z62_main_source_init(&source,memory,meta.bytes));
    CHECK(z62_main_source_publish(&source,packet,(size_t)length)==Z62_MAIN_OK);
    CHECK(z62_main_source_start(&source)==Z62_MAIN_OK && z62_main_source_begin(&source,&lease)==Z62_MAIN_OK);
    memset(packed,0xa5,(size_t)packed_bytes); memset(linear,0xa5,linear_bytes);
    CHECK(z62_capturework_pixels_pack(&c,lease.pixels,lease.meta.bytes,packed,(size_t)packed_bytes)==Z62_CW_PIXELS_OK);
    CHECK(z62_transfer_unpack(&frozen,packed,(size_t)packed_bytes,c.output_width,c.output_height,c.output_stride,
        linear,linear_bytes,linear_stride)==Z62_TRANSFER_OK);
    CHECK(!memcmp(memory,packet+96,meta.bytes));
    file=fopen(argv[9],"wb"); CHECK(file);
    CHECK(fwrite(packed,1,(size_t)packed_bytes,file)==(size_t)packed_bytes); CHECK(!fclose(file));
    file=fopen(argv[10],"wb"); CHECK(file);
    CHECK(fwrite(linear,1,linear_bytes,file)==linear_bytes); CHECK(!fclose(file));
    CHECK(z62_main_source_release(&source,&lease)==Z62_MAIN_OK); z62_main_source_stop(&source);
    free(packet); free(memory); free(packed); free(linear); return 0;
}

int main(int argc,char **argv)
{
    CHECK(argc>=3); uint8_t blob[532]; FILE *file=fopen(argv[2],"rb"); CHECK(file);
    CHECK(fread(blob,1,sizeof(blob),file)==sizeof(blob) && fgetc(file)==EOF); CHECK(!fclose(file));
    Z62RawTransfer transfer; CHECK(z62_transfer_load(&transfer,blob,sizeof(blob))==Z62_TRANSFER_OK);
    int result=1;
    if (!strcmp(argv[1],"roundtrip")) result=roundtrip(&transfer);
    if (!strcmp(argv[1],"rejects")) result=rejects(&transfer,blob);
    if (!strcmp(argv[1],"scene")) result=scene(&transfer,argc,argv);
    if (!result) printf("{\"completed\":true,\"bits\":%u,\"codec\":%u}\n",transfer.bits,transfer.codec);
    return result;
}
