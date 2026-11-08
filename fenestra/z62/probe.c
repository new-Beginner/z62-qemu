/* Research-only Fenestra loader checks. No Nikon firmware or native APIs. */
#include "fenestra_module.h"
#include "fenestra_api.h"
#include "fenestra_memory.h"
#ifdef FX_NATIVE_FORMAT_TEST
#include <stdio.h>
#endif
#include "fixtures.h"

typedef struct {
    uint32_t magic, phase, passed, failed_case, actual, expected, logs, pointer_bytes;
    uint32_t entry0, entry1;
} Result;
static Result result;
static unsigned char arena[2][4*4096] __attribute__((aligned(4096)));

static int all_value(const unsigned char *p, unsigned n, unsigned v) {
    for(unsigned i=0;i<n;++i)if(p[i]!=v)return 0;
    return 1;
}
static uint64_t pointer_value(const unsigned char *p) {
    uint64_t v=0;
    for(unsigned i=0;i<FX_MODULE_POINTER_BYTES;++i)v|=(uint64_t)p[i]<<(8u*i);
    return v;
}
#ifdef FX_TARGET_ARMV7_THUMB_EXPERIMENTAL
static int module_log(void *context,const char *message) {
    if(context!=&result.logs || fx_memcmp(message,"fenestra-arm32-r1",17))return 97;
    ++*(uint32_t *)context;
    return 0x620170;
}
#endif
static void fail(unsigned i,unsigned got,unsigned wanted) {
    result.phase=0xbad;result.failed_case=i;result.actual=got;result.expected=wanted;
}
static void check_all(void) {
    result=(Result){.magic=0x46583632,.phase=1,.pointer_bytes=FX_MODULE_POINTER_BYTES};
    for(unsigned place=0;place<2;++place)for(unsigned i=0;i<FIXTURE_COUNT;++i) {
        unsigned char *image=arena[place]+4096;
        const Fixture *f=&fixtures[i];FxModule out;
        fx_memset(arena[place],0xa5,sizeof(arena[place]));
        fx_memset(&out,0x55,sizeof(out));
        FxResult got=fx_module_prepare(f->data,f->size,f->sha,firmware_identity,0,image,8192,&out);
        if((unsigned)got!=f->expected){fail(i,(unsigned)got,f->expected);return;}
        if(got!=FX_OK) {
            if(!all_value(arena[place],sizeof(arena[place]),0xa5) || out.prepared || out.bytes) {
                fail(i,0x101,0);return;
            }
        } else {
            if(!out.prepared || out.bytes!=8192 || out.segment_count!=2 || out.relocation_count!=2 ||
               !all_value(arena[place],4096,0xa5) || !all_value(image+8192,4096,0xa5)) {
                fail(i,0x102,0);return;
            }
            for(unsigned r=0;r<2;++r) {
                const unsigned char *record=f->data+176+16*r;
                uint64_t target=0;
                for(unsigned j=0;j<8;++j)target|=(uint64_t)record[8+j]<<(8*j);
                uint64_t value=pointer_value(image+4096+r*FX_MODULE_POINTER_BYTES);
                if(value!=(uint64_t)(uintptr_t)image+target){fail(i,0x103,0);return;}
            }
            if(!all_value(image+4096+2*FX_MODULE_POINTER_BYTES,4096-2*FX_MODULE_POINTER_BYTES,0)) {
                fail(i,0x104,0);return;
            }
#ifdef FX_TARGET_ARMV7_THUMB_EXPERIMENTAL
            FxModuleServices api={FX_ABI,sizeof(api),&result.logs,module_log};
            uintptr_t entry=(uintptr_t)image+out.entry_offset;
            if(place)result.entry1=(uint32_t)entry;else result.entry0=(uint32_t)entry;
            __asm__ volatile("dsb sy; isb":::"memory"); /* reset probe: caches/MMU off */
            int returned=((FxModuleEntry)(entry|1u))(&api);
            if(returned!=0x620170 || result.logs!=place+1){fail(i,(unsigned)returned,0x620170);return;}
#endif
        }
        ++result.passed;
    }
    result.phase=2;
}
#ifdef FX_NATIVE_FORMAT_TEST
int main(void) {
    check_all();
    printf("{\"phase\":%u,\"passed\":%u,\"failed_case\":%u,\"actual\":%u,\"expected\":%u,\"pointer_bytes\":%u,\"module_executed\":false}\n",
           result.phase,result.passed,result.failed_case,result.actual,result.expected,result.pointer_bytes);
    return result.phase==2?0:1;
}
#else
void probe_main(void) {
    check_all();
    volatile uint32_t *box=(volatile uint32_t *)0x13e00000;
    const uint32_t *from=(const uint32_t *)&result;
    box[1]=0;
    for(unsigned i=0;i<sizeof(result)/4;++i)if(i!=1)box[i]=from[i];
    __asm__ volatile("dsb sy":::"memory");
    box[1]=result.phase; /* Publish completion only after the full receipt. */
    __asm__ volatile("dsb sy":::"memory");
}
#endif
