ENTRY(_start)
SECTIONS {
  . = 0x10020000;
  .text : { KEEP(*(.text.start)) *(.text*) }
  .rodata : { *(.rodata*) }
  .data : { *(.data*) }
  .bss (NOLOAD) : { . = ALIGN(4096); __bss_start = .; *(.bss*) *(COMMON) . = ALIGN(4); __bss_end = .; }
  ASSERT(. < 0x13d00000, "probe collides with mailbox/stack")
  /DISCARD/ : { *(.comment) *(.ARM.attributes) *(.ARM.exidx*) *(.ARM.extab*) }
}
