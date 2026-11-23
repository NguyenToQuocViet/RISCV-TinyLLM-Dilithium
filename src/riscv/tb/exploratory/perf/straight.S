#------------------------------------------------------------------------------
# File        : straight.S
# Description : Fetch throughput probe: two timer reads around 1024
#               independent ADDIs (no branch, no load-use); main returns 1.
# Author      : Claude Code (Anthropic)
# Date        : 2026-11-20
#------------------------------------------------------------------------------

    .text
    .globl main
main:
    li    t0, 0x0001FFF4
    lw    t1, 0(t0)
    .rept 1024
    addi  a1, a1, 1
    .endr
    lw    t2, 0(t0)
    li    a0, 1
    ret
