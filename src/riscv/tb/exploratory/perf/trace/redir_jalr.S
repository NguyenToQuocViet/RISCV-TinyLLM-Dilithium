#------------------------------------------------------------------------------
# File        : redir_jalr.S
# Description : Redirect trace probe, JALR: two code regions A and B that jump
#               to each other with jalr x0 through t0 (-> B) and t1 (-> A)
#               until i == 10 (5 loops). 4 independent ADDIs pad each region;
#               an EBREAK after each jump is a wrong-path poison. Returns 1.
# Author      : Claude Code (Anthropic)
# Date        : 2026-11-23
#------------------------------------------------------------------------------

    .text
    .globl main
main:
    li    s0, 0               # i
    li    s1, 10              # stop value
    la    t0, B
    la    t1, A
    .rept 4
    nop
    .endr

A:
    addi  s0, s0, 1
    .rept 4
    addi  t2, t2, 1
    .endr
    jalr  x0, 0(t0)           # -> B
    ebreak                    # poison: wrong path

    .balign 64
B:
    addi  s0, s0, 1
    .rept 4
    addi  t2, t2, 1
    .endr
    beq   s0, s1, EXIT        # taken only on the last pass
    jalr  x0, 0(t1)           # -> A
    ebreak                    # poison: wrong path

EXIT:
    li    a0, 1
    ret
