//-----------------------------------------------------------------------------
// File        : riscv_test.h
// Description : riscv-tests env for BASE (no CSR, no trap, no ecall). Code
//               starts at 0x0, test data goes to .data (data region). PASS
//               and FAIL store the last test number (gp) to 0x1_FFF8, then
//               status 1 or 2 to TEST_STATUS 0x1_FFFC, 8 NOPs, self-loop.
// Author      : Claude Code (Anthropic)
// Date        : 2026-11-20
//-----------------------------------------------------------------------------

#ifndef XP_RISCV_TEST_H
#define XP_RISCV_TEST_H

#define RVTEST_RV32U
#define RVTEST_RV64U

#define TESTNUM gp

#define RVTEST_CODE_BEGIN \
        .section .text.init; \
        .globl _start; \
_start: \
        li TESTNUM, 0;

#define RVTEST_CODE_END

// last test number to 0x1_FFF8, status to 0x1_FFFC (completion ABI)
#define XP_HALT(status) \
        fence; \
        li t0, 0x0001FFF8; \
        sw TESTNUM, 0(t0); \
        li t1, status; \
        sw t1, 4(t0); \
        nop; nop; nop; nop; nop; nop; nop; nop; \
        j .;

#define RVTEST_PASS XP_HALT(1)
#define RVTEST_FAIL XP_HALT(2)

#define EXTRA_DATA

#define RVTEST_DATA_BEGIN \
        .data; \
        .align 4;

#define RVTEST_DATA_END

#endif
