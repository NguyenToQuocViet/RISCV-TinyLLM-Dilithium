#------------------------------------------------------------------------------
# File        : start.S
# Description : SW test start code: set sp, clear .bss, call main, store the
#               return value to TEST_STATUS (1 pass, 2 fail), then 8 NOPs and
#               a self-loop (core-verification section 6 padding rule).
# Author      : Claude Code (Anthropic)
# Date        : 2026-11-20
#------------------------------------------------------------------------------

    .section .text.init, "ax"
    .globl _start
_start:
    li    sp, 0x0001FF00
    la    t0, __bss_start
    la    t1, __bss_end
1:  bgeu  t0, t1, 2f
    sw    zero, 0(t0)
    addi  t0, t0, 4
    j     1b
2:  call  main
    li    t0, 0x0001FFFC
    sw    a0, 0(t0)
    .rept 8
    addi  x0, x0, 0
    .endr
3:  j     3b
