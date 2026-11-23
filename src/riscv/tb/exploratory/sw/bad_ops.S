#------------------------------------------------------------------------------
# File        : bad_ops.S
# Description : Gate negative control: holds mul and ecall, outside BASE.
#               check_ops must reject the image built from this file.
# Author      : Claude Code (Anthropic)
# Date        : 2026-11-20
#------------------------------------------------------------------------------

    .section .text.init, "ax"
    .globl _start
_start:
    mul   t0, t1, t2
    ecall
1:  j     1b
