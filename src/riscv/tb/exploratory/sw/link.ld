/*-----------------------------------------------------------------------------
 * File        : link.ld
 * Description : SW test layout. Code region 0x0..0xFFFF; every data section,
 *               rodata included, in the data region (the data port serves
 *               0x1_0000 and up only). Stack top 0x1_FF00, signature
 *               0x1_FF00..0x1_FFF8, TEST_STATUS 0x1_FFFC.
 * Author      : Claude Code (Anthropic)
 * Date        : 2026-11-20
 *---------------------------------------------------------------------------*/

OUTPUT_ARCH("riscv")
ENTRY(_start)

MEMORY
{
  CODE (rx) : ORIGIN = 0x00000000, LENGTH = 0x10000
  DATA (rw) : ORIGIN = 0x00010000, LENGTH = 0xF000
}

SECTIONS
{
  .text : {
    KEEP(*(.text.init))
    *(.text .text.*)
  } > CODE

  .rodata : { *(.rodata .rodata.* .srodata .srodata.*) } > DATA
  .data   : { *(.data .data.* .sdata .sdata.*) } > DATA
  .bss (NOLOAD) : {
    __bss_start = .;
    *(.bss .bss.* .sbss .sbss.* COMMON)
    . = ALIGN(4);
    __bss_end = .;
  } > DATA

  /DISCARD/ : { *(.comment) *(.riscv.attributes) *(.note*) *(.eh_frame*) }
}

__stack_top = 0x0001FF00;
ASSERT(__bss_end <= 0x0001F000, "data sections overflow into the stack area")
