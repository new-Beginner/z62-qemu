/* Synthetic no-firmware probe boot; not a Nikon startup hook.
 * Exceptions are recorded then halted, never bypassed or marked successful.
 */
.syntax unified
.arm
.section .text.start,"ax",%progbits
.global _start
.type _start,%function
_start:
    ldr sp,=0x13f00000
    ldr r0,=.Lvectors
    mcr p15,0,r0,c12,c0,0
    isb
    ldr r0,=__bss_start
    ldr r1,=__bss_end
    mov r2,#0
1:  cmp r0,r1
    strlo r2,[r0],#4
    blo 1b
    bl probe_main
2:  b 2b
.size _start,.-_start
.balign 32
.Lvectors:
.rept 8
    b .Lfault
.endr
.Lfault:
    ldr r0,=0x13e00000
    mov r1,#0
    str r1,[r0,#4]
    ldr r1,=0x46583632
    str r1,[r0,#0]
    mov r1,#-1
    str r1,[r0,#12] /* sentinel: exception, not a format test case */
    str lr,[r0,#16]
    mrc p15,0,r2,c5,c0,0
    str r2,[r0,#20] /* DFSR */
    mrc p15,0,r2,c6,c0,0
    str r2,[r0,#24] /* DFAR */
    mrc p15,0,r2,c5,c0,1
    str r2,[r0,#28] /* IFSR */
    mrc p15,0,r2,c6,c0,2
    str r2,[r0,#32] /* IFAR */
    mrs r2,spsr
    str r2,[r0,#36]
    dsb sy
    ldr r1,=0xbad
    str r1,[r0,#4]
    dsb sy
3:  b 3b
