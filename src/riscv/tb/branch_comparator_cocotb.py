#------------------------------------------------------------------------------
# Module      : branch_comparator_cocotb
# Description : Branch comparator reference model, directed and random tests.
# Author      : Viet Nguyen To Quoc
# Date        : 2026-10-17
#------------------------------------------------------------------------------

import cocotb
import random
from cocotb.triggers import Timer
from ctypes import c_int32, c_uint32

BR_EQ          = 0b000
BR_NE          = 0b001
BR_LT_SIGNED   = 0b100
BR_GE_SIGNED   = 0b101
BR_LT_UNSIGNED = 0b110
BR_GE_UNSIGNED = 0b111

def branch_comparator_golden(a, b, kind):
    a_unsigned = c_uint32(a).value
    b_unsigned = c_uint32(b).value
    a_signed = c_int32(a).value
    b_signed = c_int32(b).value

    if kind == BR_EQ:
        result = a_unsigned == b_unsigned
    elif kind == BR_NE:
        result = a_unsigned != b_unsigned
    elif kind == BR_LT_SIGNED:
        result = a_signed < b_signed
    elif kind == BR_GE_SIGNED:
        result = a_signed >= b_signed
    elif kind == BR_LT_UNSIGNED:
        result = a_unsigned < b_unsigned
    elif kind == BR_GE_UNSIGNED:
        result = a_unsigned >= b_unsigned
    elif kind in (0b010, 0b011):
        result = False
    else:
        raise ValueError(f"Branch selector is outside the 3-bit domain: {kind}")

    return int(result)

async def check_branch_comparator(dut, a, b, kind, expected):
    dut.operand_a.value   = c_uint32(a).value
    dut.operand_b.value   = c_uint32(b).value
    dut.branch_kind.value = kind

    await Timer(1, unit="ns")

    result = int(dut.branch_condition.value)
    assert result == expected, (
        f"kind={kind:03b}, a=0x{c_uint32(a).value:08X}, "
        f"b=0x{c_uint32(b).value:08X}: expected {expected}, got {result}"
    )


@cocotb.test()
async def test_eq(dut):
    #TEST1 ordinary equality and inequality
    await check_branch_comparator(dut, 20, 20, BR_EQ, 1)
    await check_branch_comparator(dut, 20, 26, BR_EQ, 0)
    await check_branch_comparator(dut, 26, 20, BR_EQ, 0)
    await check_branch_comparator(dut, -20, -20, BR_EQ, 1)
    await check_branch_comparator(dut, -20, 20, BR_EQ, 0)

    #TEST2 equal extrema, adjacent boundary values and a difference in each bit
    await check_branch_comparator(dut, 0x7FFF_FFFF, 0x7FFF_FFFF, BR_EQ, 1)
    await check_branch_comparator(dut, 0x8000_0000, 0x8000_0000, BR_EQ, 1)
    await check_branch_comparator(dut, 0xFFFF_FFFF, 0xFFFF_FFFF, BR_EQ, 1)
    await check_branch_comparator(dut, 0x7FFF_FFFF, 0x8000_0000, BR_EQ, 0)
    await check_branch_comparator(dut, 0xFFFF_FFFE, 0xFFFF_FFFF, BR_EQ, 0)
    for bit in range(32):
        await check_branch_comparator(dut, 0, 1 << bit, BR_EQ, 0)
        await check_branch_comparator(dut, 1 << bit, 0, BR_EQ, 0)

    #TEST3 zero equals zero
    await check_branch_comparator(dut, 0, 0, BR_EQ, 1)

    #TEST4 random full-width operands checked against the golden model
    rng = random.Random(2026)
    for _ in range(100000):
        a = rng.getrandbits(32)
        b = rng.getrandbits(32)
        expected = branch_comparator_golden(a, b, BR_EQ)

        await check_branch_comparator(dut, a, b, BR_EQ, expected)


@cocotb.test()
async def test_ne(dut):
    #TEST1 ordinary inequality and equality
    await check_branch_comparator(dut, 20, 26, BR_NE, 1)
    await check_branch_comparator(dut, 26, 20, BR_NE, 1)
    await check_branch_comparator(dut, 20, 20, BR_NE, 0)
    await check_branch_comparator(dut, -20, -20, BR_NE, 0)
    await check_branch_comparator(dut, -20, 20, BR_NE, 1)

    #TEST2 equal extrema, adjacent boundary values and a difference in each bit
    await check_branch_comparator(dut, 0x7FFF_FFFF, 0x7FFF_FFFF, BR_NE, 0)
    await check_branch_comparator(dut, 0x8000_0000, 0x8000_0000, BR_NE, 0)
    await check_branch_comparator(dut, 0xFFFF_FFFF, 0xFFFF_FFFF, BR_NE, 0)
    await check_branch_comparator(dut, 0x7FFF_FFFF, 0x8000_0000, BR_NE, 1)
    await check_branch_comparator(dut, 0xFFFF_FFFE, 0xFFFF_FFFF, BR_NE, 1)
    for bit in range(32):
        await check_branch_comparator(dut, 0, 1 << bit, BR_NE, 1)
        await check_branch_comparator(dut, 1 << bit, 0, BR_NE, 1)

    #TEST3 zero is not different from zero
    await check_branch_comparator(dut, 0, 0, BR_NE, 0)

    #TEST4 random full-width operands checked against the golden model
    rng = random.Random(2026)
    for _ in range(100000):
        a = rng.getrandbits(32)
        b = rng.getrandbits(32)
        expected = branch_comparator_golden(a, b, BR_NE)

        await check_branch_comparator(dut, a, b, BR_NE, expected)


@cocotb.test()
async def test_lt_signed(dut):
    #TEST1 signed ordering within each sign group and ordinary equality
    await check_branch_comparator(dut, 20, 26, BR_LT_SIGNED, 1)
    await check_branch_comparator(dut, 26, 20, BR_LT_SIGNED, 0)
    await check_branch_comparator(dut, -26, -20, BR_LT_SIGNED, 1)
    await check_branch_comparator(dut, -20, -26, BR_LT_SIGNED, 0)
    await check_branch_comparator(dut, 20, 20, BR_LT_SIGNED, 0)

    #TEST2 signed extrema, adjacent values, cross-sign ordering and equality
    await check_branch_comparator(dut, 0x8000_0000, 0x7FFF_FFFF, BR_LT_SIGNED, 1)
    await check_branch_comparator(dut, 0x7FFF_FFFF, 0x8000_0000, BR_LT_SIGNED, 0)
    await check_branch_comparator(dut, 0x8000_0000, 0x8000_0001, BR_LT_SIGNED, 1)
    await check_branch_comparator(dut, 0x8000_0001, 0x8000_0000, BR_LT_SIGNED, 0)
    await check_branch_comparator(dut, 0x7FFF_FFFE, 0x7FFF_FFFF, BR_LT_SIGNED, 1)
    await check_branch_comparator(dut, 0x7FFF_FFFF, 0x7FFF_FFFE, BR_LT_SIGNED, 0)
    await check_branch_comparator(dut, 0x8000_0000, 0x8000_0000, BR_LT_SIGNED, 0)
    await check_branch_comparator(dut, 0x7FFF_FFFF, 0x7FFF_FFFF, BR_LT_SIGNED, 0)
    await check_branch_comparator(dut, -1, 0, BR_LT_SIGNED, 1)
    await check_branch_comparator(dut, 0, -1, BR_LT_SIGNED, 0)
    await check_branch_comparator(dut, 0, 1, BR_LT_SIGNED, 1)
    await check_branch_comparator(dut, 1, 0, BR_LT_SIGNED, 0)

    #TEST3 zero is not strictly less than zero
    await check_branch_comparator(dut, 0, 0, BR_LT_SIGNED, 0)

    #TEST4 random full-width operands checked against the golden model
    rng = random.Random(2026)
    for _ in range(100000):
        a = rng.getrandbits(32)
        b = rng.getrandbits(32)
        expected = branch_comparator_golden(a, b, BR_LT_SIGNED)

        await check_branch_comparator(dut, a, b, BR_LT_SIGNED, expected)


@cocotb.test()
async def test_ge_signed(dut):
    #TEST1 signed ordering within each sign group and ordinary equality
    await check_branch_comparator(dut, 20, 26, BR_GE_SIGNED, 0)
    await check_branch_comparator(dut, 26, 20, BR_GE_SIGNED, 1)
    await check_branch_comparator(dut, -26, -20, BR_GE_SIGNED, 0)
    await check_branch_comparator(dut, -20, -26, BR_GE_SIGNED, 1)
    await check_branch_comparator(dut, 20, 20, BR_GE_SIGNED, 1)

    #TEST2 signed extrema, adjacent values, cross-sign ordering and equality
    await check_branch_comparator(dut, 0x8000_0000, 0x7FFF_FFFF, BR_GE_SIGNED, 0)
    await check_branch_comparator(dut, 0x7FFF_FFFF, 0x8000_0000, BR_GE_SIGNED, 1)
    await check_branch_comparator(dut, 0x8000_0000, 0x8000_0001, BR_GE_SIGNED, 0)
    await check_branch_comparator(dut, 0x8000_0001, 0x8000_0000, BR_GE_SIGNED, 1)
    await check_branch_comparator(dut, 0x7FFF_FFFE, 0x7FFF_FFFF, BR_GE_SIGNED, 0)
    await check_branch_comparator(dut, 0x7FFF_FFFF, 0x7FFF_FFFE, BR_GE_SIGNED, 1)
    await check_branch_comparator(dut, 0x8000_0000, 0x8000_0000, BR_GE_SIGNED, 1)
    await check_branch_comparator(dut, 0x7FFF_FFFF, 0x7FFF_FFFF, BR_GE_SIGNED, 1)
    await check_branch_comparator(dut, -1, 0, BR_GE_SIGNED, 0)
    await check_branch_comparator(dut, 0, -1, BR_GE_SIGNED, 1)
    await check_branch_comparator(dut, 0, 1, BR_GE_SIGNED, 0)
    await check_branch_comparator(dut, 1, 0, BR_GE_SIGNED, 1)

    #TEST3 zero is greater than or equal to zero
    await check_branch_comparator(dut, 0, 0, BR_GE_SIGNED, 1)

    #TEST4 random full-width operands checked against the golden model
    rng = random.Random(2026)
    for _ in range(100000):
        a = rng.getrandbits(32)
        b = rng.getrandbits(32)
        expected = branch_comparator_golden(a, b, BR_GE_SIGNED)

        await check_branch_comparator(dut, a, b, BR_GE_SIGNED, expected)


@cocotb.test()
async def test_lt_unsigned(dut):
    #TEST1 unsigned ordering below and above the MSB boundary and equality
    await check_branch_comparator(dut, 20, 26, BR_LT_UNSIGNED, 1)
    await check_branch_comparator(dut, 26, 20, BR_LT_UNSIGNED, 0)
    await check_branch_comparator(dut, 0x8000_0020, 0x8000_0026, BR_LT_UNSIGNED, 1)
    await check_branch_comparator(dut, 0x8000_0026, 0x8000_0020, BR_LT_UNSIGNED, 0)
    await check_branch_comparator(dut, 20, 20, BR_LT_UNSIGNED, 0)

    #TEST2 zero/minimum, unsigned maximum, MSB boundary and equal extrema
    await check_branch_comparator(dut, 0, 1, BR_LT_UNSIGNED, 1)
    await check_branch_comparator(dut, 1, 0, BR_LT_UNSIGNED, 0)
    await check_branch_comparator(dut, 0, 0xFFFF_FFFF, BR_LT_UNSIGNED, 1)
    await check_branch_comparator(dut, 0xFFFF_FFFF, 0, BR_LT_UNSIGNED, 0)
    await check_branch_comparator(dut, 0x7FFF_FFFF, 0x8000_0000, BR_LT_UNSIGNED, 1)
    await check_branch_comparator(dut, 0x8000_0000, 0x7FFF_FFFF, BR_LT_UNSIGNED, 0)
    await check_branch_comparator(dut, 0xFFFF_FFFE, 0xFFFF_FFFF, BR_LT_UNSIGNED, 1)
    await check_branch_comparator(dut, 0xFFFF_FFFF, 0xFFFF_FFFE, BR_LT_UNSIGNED, 0)
    await check_branch_comparator(dut, 0x8000_0000, 0x8000_0000, BR_LT_UNSIGNED, 0)
    await check_branch_comparator(dut, 0xFFFF_FFFF, 0xFFFF_FFFF, BR_LT_UNSIGNED, 0)

    #TEST3 zero is not strictly less than zero
    await check_branch_comparator(dut, 0, 0, BR_LT_UNSIGNED, 0)

    #TEST4 random full-width operands checked against the golden model
    rng = random.Random(2026)
    for _ in range(100000):
        a = rng.getrandbits(32)
        b = rng.getrandbits(32)
        expected = branch_comparator_golden(a, b, BR_LT_UNSIGNED)

        await check_branch_comparator(dut, a, b, BR_LT_UNSIGNED, expected)


@cocotb.test()
async def test_ge_unsigned(dut):
    #TEST1 unsigned ordering below and above the MSB boundary and equality
    await check_branch_comparator(dut, 20, 26, BR_GE_UNSIGNED, 0)
    await check_branch_comparator(dut, 26, 20, BR_GE_UNSIGNED, 1)
    await check_branch_comparator(dut, 0x8000_0020, 0x8000_0026, BR_GE_UNSIGNED, 0)
    await check_branch_comparator(dut, 0x8000_0026, 0x8000_0020, BR_GE_UNSIGNED, 1)
    await check_branch_comparator(dut, 20, 20, BR_GE_UNSIGNED, 1)

    #TEST2 zero/minimum, unsigned maximum, MSB boundary and equal extrema
    await check_branch_comparator(dut, 0, 1, BR_GE_UNSIGNED, 0)
    await check_branch_comparator(dut, 1, 0, BR_GE_UNSIGNED, 1)
    await check_branch_comparator(dut, 0, 0xFFFF_FFFF, BR_GE_UNSIGNED, 0)
    await check_branch_comparator(dut, 0xFFFF_FFFF, 0, BR_GE_UNSIGNED, 1)
    await check_branch_comparator(dut, 0x7FFF_FFFF, 0x8000_0000, BR_GE_UNSIGNED, 0)
    await check_branch_comparator(dut, 0x8000_0000, 0x7FFF_FFFF, BR_GE_UNSIGNED, 1)
    await check_branch_comparator(dut, 0xFFFF_FFFE, 0xFFFF_FFFF, BR_GE_UNSIGNED, 0)
    await check_branch_comparator(dut, 0xFFFF_FFFF, 0xFFFF_FFFE, BR_GE_UNSIGNED, 1)
    await check_branch_comparator(dut, 0x8000_0000, 0x8000_0000, BR_GE_UNSIGNED, 1)
    await check_branch_comparator(dut, 0xFFFF_FFFF, 0xFFFF_FFFF, BR_GE_UNSIGNED, 1)

    #TEST3 zero is greater than or equal to zero
    await check_branch_comparator(dut, 0, 0, BR_GE_UNSIGNED, 1)

    #TEST4 random full-width operands checked against the golden model
    rng = random.Random(2026)
    for _ in range(100000):
        a = rng.getrandbits(32)
        b = rng.getrandbits(32)
        expected = branch_comparator_golden(a, b, BR_GE_UNSIGNED)

        await check_branch_comparator(dut, a, b, BR_GE_UNSIGNED, expected)
