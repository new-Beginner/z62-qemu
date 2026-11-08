/* ARM EABI memory adapters for the integer-only research loader.
 * Do not pull a toolchain's SIMD memcpy into a context with no FP ownership.
 * EABI memset argument order differs from ISO C: destination, bytes, value.
 */
#include "fenestra_memory.h"
#define COPY(name) void name(void *d,const void *s,size_t n){(void)fx_memcpy(d,s,n);}
#define MOVE(name) void name(void *d,const void *s,size_t n){(void)fx_memmove(d,s,n);}
#define SET(name) void name(void *d,size_t n,int c){(void)fx_memset(d,c,n);}
#define CLEAR(name) void name(void *d,size_t n){(void)fx_memset(d,0,n);}
COPY(__aeabi_memcpy)
COPY(__aeabi_memcpy4)
COPY(__aeabi_memcpy8)
MOVE(__aeabi_memmove)
MOVE(__aeabi_memmove4)
MOVE(__aeabi_memmove8)
SET(__aeabi_memset)
SET(__aeabi_memset4)
SET(__aeabi_memset8)
CLEAR(__aeabi_memclr)
CLEAR(__aeabi_memclr4)
CLEAR(__aeabi_memclr8)
