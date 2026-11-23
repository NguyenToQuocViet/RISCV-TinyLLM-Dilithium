//-----------------------------------------------------------------------------
// File        : test_macros.h
// Description : Wrapper over the riscv-tests scalar test_macros.h. Negative
//               controls only: XP_BREAK_CASE=N flips bit 0 of the expected
//               value of test case N; XP_BREAK_ALL flips it in every
//               TEST_CASE. Without either define the upstream macros apply.
// Author      : Claude Code (Anthropic)
// Date        : 2026-11-20
//-----------------------------------------------------------------------------

#ifndef XP_TEST_MACROS_H
#define XP_TEST_MACROS_H

#include_next "test_macros.h"

#if defined(XP_BREAK_ALL)
#define XP_EXPECT(n, v) ((v) ^ 0x00000001)
#elif defined(XP_BREAK_CASE)
#define XP_EXPECT(n, v) ((v) ^ (((n) == XP_BREAK_CASE) & 1))
#endif

#ifdef XP_EXPECT
#undef TEST_CASE
#define TEST_CASE( testnum, testreg, correctval, code... ) \
test_ ## testnum: \
    li  TESTNUM, testnum; \
    code; \
    li  x7, MASK_XLEN(XP_EXPECT(testnum, correctval)); \
    bne testreg, x7, fail;
#endif

#endif
