ENTRY(fenestra_module_entry)
SECTIONS {
  . = 0;
  .text : { *(.text*) *(.rodata*) }
  /DISCARD/ : { *(.comment) *(.ARM.attributes) *(.ARM.exidx*) *(.ARM.extab*) }
}
