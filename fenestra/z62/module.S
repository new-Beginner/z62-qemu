/* Local original test module; FxModuleServices legacy entry, ARM32 only. */
.syntax unified
.thumb
.section .text,"ax",%progbits
.hword 0xbf00 /* Entry deliberately at offset 2, not AArch64's alignment. */
.global fenestra_module_entry
.type fenestra_module_entry,%function
.thumb_func
fenestra_module_entry:
.Lentry:
    push {r4,lr}
    cmp r0,#0
    beq .Lbad
    ldr r2,[r0,#0]
    cmp r2,#1
    bne .Lbad
    ldr r2,[r0,#4]
    cmp r2,#16
    bne .Lbad
    adr.w r3,.Lentry
    sub.w r3,r3,#2
    movw r2,#4096
    add r3,r3,r2
    ldr r1,[r3,#0] /* relocated message pointer */
    ldr r3,[r3,#4] /* independently relocated Thumb helper pointer */
    blx r3
    pop {r4,pc}
.Lbad:
    movs r0,#99
    pop {r4,pc}
.size fenestra_module_entry,.-fenestra_module_entry
.global module_helper
.type module_helper,%function
.thumb_func
module_helper:
    ldr r2,[r0,#8]
    ldr r3,[r0,#12]
    mov r0,r2
    bx r3
.size module_helper,.-module_helper
.balign 4
.global module_message
module_message:
    .asciz "fenestra-arm32-r1"
.balign 4
