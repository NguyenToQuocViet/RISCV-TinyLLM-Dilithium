#------------------------------------------------------------------------------
# File        : redir_beq.S
# Description : Redirect trace probe, BEQ: two code regions A and B that jump
#               to each other with an always-taken beq x0,x0 until i == 10
#               (5 loops). 4 independent ADDIs pad each region; an EBREAK
#               after each jump is a wrong-path poison. Returns 1.
# Author      : Claude Code (Anthropic)
# Date        : 2026-11-23
#------------------------------------------------------------------------------

    .text
    .globl main
main:
    li    s0, 0               # i
    li    s1, 10              # stop value
    .rept 4
    nop
    .endr

A:
    addi  s0, s0, 1
    .rept 4
    addi  t2, t2, 1
    .endr
    beq   x0, x0, B           # always taken
    ebreak                    # poison: wrong path

    .balign 64
B:
    addi  s0, s0, 1
    .rept 4
    addi  t2, t2, 1
    .endr
    beq   s0, s1, EXIT        # taken only on the last pass
    beq   x0, x0, A           # always taken
    ebreak                    # poison: wrong path

EXIT:
    li    a0, 1
    ret
