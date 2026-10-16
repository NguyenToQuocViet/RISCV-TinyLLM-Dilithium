#------------------------------------------------------------------------------
# Module      : alu_cocotb
# Description : ALU reference model and directed and random cocotb tests.
# Author      : Viet Nguyen To Quoc
# Date        : 2026-10-16
#------------------------------------------------------------------------------

import cocotb
import random
from cocotb.triggers import Timer
from ctypes import c_int32, c_uint32

def alu_golden(a, b, op):
    a_unsigned = c_uint32(a).value
    b_unsigned = c_uint32(b).value
    a_signed = c_int32(a).value
    b_signed = c_int32(b).value
    shamt = b_unsigned & 0x1F

    if op == 0:       # ADD
        result = a_signed + b_signed
    elif op == 1:     # SUB
        result = a_signed - b_signed
    elif op == 2:     # AND
        result = a_unsigned & b_unsigned
    elif op == 3:     # OR
        result = a_unsigned | b_unsigned
    elif op == 4:     # XOR
        result = a_unsigned ^ b_unsigned
    elif op == 5:     # SLL
        result = a_unsigned << shamt
    elif op == 6:     # SRL
        result = a_unsigned >> shamt
    elif op == 7:     # SRA
        result = a_signed >> shamt
    elif op == 8:     # SLT
        result = int(a_signed < b_signed)
    elif op == 9:     # SLTU
        result = int(a_unsigned < b_unsigned)
    else:
        raise ValueError(f"Unsupported operation in reference model: {op}")

    return c_int32(result).value

async def check_alu(dut, a, b, op):
    expected = alu_golden(a, b, op)

    dut.operand_a.value = a
    dut.operand_b.value = b
    dut.alu_op.value    = op

    await Timer(1, unit="ns")

    result = dut.alu_result.value.to_signed()
    assert result == expected, (
        f"op={op}, a={a}, b={b}: "
        f"expected {expected}, got {result}"
    )

@cocotb.test()
async def test_add(dut):
    #TEST1 ordinary addition with positive and negative operands
    await check_alu(dut, 20, 26, 0)
    await check_alu(dut, 10, 16, 0)
    await check_alu(dut, 1234, 5678, 0)
    await check_alu(dut, 2, -3, 0)
    await check_alu(dut, -20, -26, 0)

    #TEST2 add 0
    await check_alu(dut, 2, 0, 0)
    await check_alu(dut, 0, 3, 0)
    await check_alu(dut, 0, 0, 0)

    #TEST3 32-bit wrap and signed overflow, in both operand orders
    await check_alu(dut, 0xFFFF_FFFF, 1, 0)
    await check_alu(dut, 0x7FFF_FFFF, 1, 0)
    await check_alu(dut, 1, 0xFFFF_FFFF, 0)
    await check_alu(dut, 1, 0x7FFF_FFFF, 0)
    await check_alu(dut, 0x8000_0000, -1, 0)
    await check_alu(dut, -1, 0x8000_0000, 0)

    #TEST4 random add
    rng = random.Random(2026)
    for _ in range(100000):
        a = rng.getrandbits(32)
        b = rng.getrandbits(32)

        await check_alu(dut, a, b, 0)

@cocotb.test()
async def test_sub(dut):
    #TEST1 ordinary subtraction with positive and negative results
    await check_alu(dut, 20, 26, 1)
    await check_alu(dut, 10, 16, 1)
    await check_alu(dut, 5678, 1234, 1)
    await check_alu(dut, -20, -26, 1)
    await check_alu(dut, 20, -26, 1)

    #TEST2 zero on either input and equal operands
    await check_alu(dut, 2, 0, 1)
    await check_alu(dut, 0, 3, 1)
    await check_alu(dut, 0, 0, 1)
    await check_alu(dut, 26, 26, 1)

    #TEST3 32-bit underflow and both signed overflow directions
    await check_alu(dut, 0, 0xFFFF_FFFF, 1)
    await check_alu(dut, 0, 1, 1)
    await check_alu(dut, 0x8000_0000, 1, 1)
    await check_alu(dut, 0x7FFF_FFFF, -1, 1)

    #TEST4 random sub
    rng = random.Random(2026)
    for _ in range(100000):
        a = rng.getrandbits(32)
        b = rng.getrandbits(32)

        await check_alu(dut, a, b, 1)


@cocotb.test()
async def test_and(dut):
    #TEST1 retain only bits set in both operands
    await check_alu(dut, 0x0000_00CC, 0x0000_00AA, 2)
    await check_alu(dut, 0x1234_5678, 0x0F0F_0F0F, 2)
    await check_alu(dut, 0x0F0F_0F0F, 0x1234_5678, 2)

    #TEST2 zero clears all bits; all ones preserve the other operand
    await check_alu(dut, 0x1234_5678, 0, 2)
    await check_alu(dut, 0, 0x1234_5678, 2)
    await check_alu(dut, 0x1234_5678, 0xFFFF_FFFF, 2)
    await check_alu(dut, 0xFFFF_FFFF, 0x1234_5678, 2)

    #TEST3 MSB/LSB isolation and complementary alternating patterns
    await check_alu(dut, 0x8000_0000, 0x8000_0000, 2)
    await check_alu(dut, 0x8000_0000, 0x7FFF_FFFF, 2)
    await check_alu(dut, 0x0000_0001, 0xFFFF_FFFF, 2)
    await check_alu(dut, 0xAAAA_AAAA, 0x5555_5555, 2)

    #TEST4 random and
    rng = random.Random(2026)
    for _ in range(100000):
        a = rng.getrandbits(32)
        b = rng.getrandbits(32)

        await check_alu(dut, a, b, 2)


@cocotb.test()
async def test_or(dut):
    #TEST1 retain bits set in either operand
    await check_alu(dut, 0x0000_00CC, 0x0000_00AA, 3)
    await check_alu(dut, 0x1234_5678, 0x0F0F_0F0F, 3)
    await check_alu(dut, 0x0F0F_0F0F, 0x1234_5678, 3)

    #TEST2 zero preserves the other operand; all ones set every bit
    await check_alu(dut, 0x1234_5678, 0, 3)
    await check_alu(dut, 0, 0x1234_5678, 3)
    await check_alu(dut, 0x1234_5678, 0xFFFF_FFFF, 3)
    await check_alu(dut, 0xFFFF_FFFF, 0x1234_5678, 3)

    #TEST3 MSB/LSB isolation and complementary alternating patterns
    await check_alu(dut, 0x8000_0000, 0, 3)
    await check_alu(dut, 0, 0x0000_0001, 3)
    await check_alu(dut, 0x8000_0000, 0x7FFF_FFFF, 3)
    await check_alu(dut, 0xAAAA_AAAA, 0x5555_5555, 3)

    #TEST4 random or
    rng = random.Random(2026)
    for _ in range(100000):
        a = rng.getrandbits(32)
        b = rng.getrandbits(32)

        await check_alu(dut, a, b, 3)


@cocotb.test()
async def test_xor(dut):
    #TEST1 retain only bits that differ between operands
    await check_alu(dut, 0x0000_00CC, 0x0000_00AA, 4)
    await check_alu(dut, 0x1234_5678, 0x0F0F_0F0F, 4)
    await check_alu(dut, 0x0F0F_0F0F, 0x1234_5678, 4)

    #TEST2 zero preserves, equal operands clear, all ones invert
    await check_alu(dut, 0x1234_5678, 0, 4)
    await check_alu(dut, 0, 0x1234_5678, 4)
    await check_alu(dut, 0x1234_5678, 0x1234_5678, 4)
    await check_alu(dut, 0x1234_5678, 0xFFFF_FFFF, 4)
    await check_alu(dut, 0xFFFF_FFFF, 0x1234_5678, 4)

    #TEST3 MSB/LSB isolation and complementary alternating patterns
    await check_alu(dut, 0x8000_0000, 0x7FFF_FFFF, 4)
    await check_alu(dut, 0x8000_0000, 0xFFFF_FFFF, 4)
    await check_alu(dut, 0x0000_0001, 0xFFFF_FFFF, 4)
    await check_alu(dut, 0xAAAA_AAAA, 0x5555_5555, 4)

    #TEST4 random xor
    rng = random.Random(2026)
    for _ in range(100000):
        a = rng.getrandbits(32)
        b = rng.getrandbits(32)

        await check_alu(dut, a, b, 4)


@cocotb.test()
async def test_sll(dut):
    #TEST1 shift left by ordinary amounts and zero-fill low bits
    await check_alu(dut, 0x0000_0013, 1, 5)
    await check_alu(dut, 0x0000_0013, 4, 5)
    await check_alu(dut, 0x1234_5678, 8, 5)

    #TEST2 zero shift preserves A; zero A stays zero
    await check_alu(dut, 0x89AB_CDEF, 0, 5)
    await check_alu(dut, 0, 0, 5)
    await check_alu(dut, 0, 31, 5)

    #TEST3 maximum shift, discarded high bits and ignored B[31:5]
    await check_alu(dut, 1, 31, 5)
    await check_alu(dut, 0xFFFF_FFFF, 31, 5)
    await check_alu(dut, 0x8000_0000, 1, 5)
    await check_alu(dut, 0x89AB_CDEF, 32, 5)  #shamt=0
    await check_alu(dut, 0x89AB_CDEF, 33, 5)  #shamt=1
    await check_alu(dut, 0x89AB_CDEF, 63, 5)  #shamt=31
    await check_alu(dut, 0x89AB_CDEF, 0xFFFF_FFE0, 5)  #shamt=0
    await check_alu(dut, 0x89AB_CDEF, 0xFFFF_FFFF, 5)  #shamt=31

    #TEST4 random sll, including random unused high bits of B
    rng = random.Random(2026)
    for _ in range(100000):
        a = rng.getrandbits(32)
        b = rng.getrandbits(32)

        await check_alu(dut, a, b, 5)


@cocotb.test()
async def test_srl(dut):
    #TEST1 shift right and zero-fill even when A[31] is one
    await check_alu(dut, 0x0000_0013, 1, 6)
    await check_alu(dut, 0x1234_5678, 4, 6)
    await check_alu(dut, 0x8000_0000, 1, 6)

    #TEST2 zero shift preserves A; zero A stays zero
    await check_alu(dut, 0x89AB_CDEF, 0, 6)
    await check_alu(dut, 0, 0, 6)
    await check_alu(dut, 0, 31, 6)

    #TEST3 maximum shift, discarded low bits and ignored B[31:5]
    await check_alu(dut, 0x8000_0000, 31, 6)
    await check_alu(dut, 0xFFFF_FFFF, 31, 6)
    await check_alu(dut, 1, 1, 6)
    await check_alu(dut, 0x89AB_CDEF, 32, 6)  #shamt=0
    await check_alu(dut, 0x89AB_CDEF, 33, 6)  #shamt=1
    await check_alu(dut, 0x89AB_CDEF, 63, 6)  #shamt=31
    await check_alu(dut, 0x89AB_CDEF, 0xFFFF_FFE0, 6)  #shamt=0
    await check_alu(dut, 0x89AB_CDEF, 0xFFFF_FFFF, 6)  #shamt=31

    #TEST4 random srl, including random unused high bits of B
    rng = random.Random(2026)
    for _ in range(100000):
        a = rng.getrandbits(32)
        b = rng.getrandbits(32)

        await check_alu(dut, a, b, 6)


@cocotb.test()
async def test_sra(dut):
    #TEST1 shift right with zero-fill for positive A, sign-fill for negative A
    await check_alu(dut, 0x1234_5678, 4, 7)
    await check_alu(dut, -20, 2, 7)
    await check_alu(dut, -3, 1, 7)  #arithmetic shift rounds toward negative infinity

    #TEST2 zero shift preserves A; zero and minus one remain unchanged
    await check_alu(dut, 0x89AB_CDEF, 0, 7)
    await check_alu(dut, 0, 31, 7)
    await check_alu(dut, -1, 1, 7)
    await check_alu(dut, -1, 31, 7)

    #TEST3 signed extrema, maximum shift and ignored B[31:5]
    await check_alu(dut, 0x8000_0000, 1, 7)
    await check_alu(dut, 0x8000_0000, 31, 7)
    await check_alu(dut, 0x7FFF_FFFF, 31, 7)
    await check_alu(dut, 0x89AB_CDEF, 32, 7)  #shamt=0
    await check_alu(dut, 0x89AB_CDEF, 33, 7)  #shamt=1
    await check_alu(dut, 0x89AB_CDEF, 63, 7)  #shamt=31
    await check_alu(dut, 0x89AB_CDEF, 0xFFFF_FFE0, 7)  #shamt=0
    await check_alu(dut, 0x89AB_CDEF, 0xFFFF_FFFF, 7)  #shamt=31

    #TEST4 random sra, including random unused high bits of B
    rng = random.Random(2026)
    for _ in range(100000):
        a = rng.getrandbits(32)
        b = rng.getrandbits(32)

        await check_alu(dut, a, b, 7)


@cocotb.test()
async def test_slt(dut):
    #TEST1 signed less-than: both outcomes within each sign group
    await check_alu(dut, 20, 26, 8)
    await check_alu(dut, 26, 20, 8)
    await check_alu(dut, -26, -20, 8)
    await check_alu(dut, -20, -26, 8)

    #TEST2 equality is false; compare zero against both signs
    await check_alu(dut, 26, 26, 8)
    await check_alu(dut, -26, -26, 8)
    await check_alu(dut, 0, 0, 8)
    await check_alu(dut, -1, 0, 8)
    await check_alu(dut, 0, -1, 8)
    await check_alu(dut, 0, 1, 8)
    await check_alu(dut, 1, 0, 8)

    #TEST3 signed extrema, cross-sign ordering and full-width result
    await check_alu(dut, 0x8000_0000, 0x7FFF_FFFF, 8)
    await check_alu(dut, 0x7FFF_FFFF, 0x8000_0000, 8)
    await check_alu(dut, 0xFFFF_FFFF, 1, 8)
    await check_alu(dut, 1, 0xFFFF_FFFF, 8)
    await check_alu(dut, 0x8000_0000, 0x8000_0000, 8)
    await check_alu(dut, 0x7FFF_FFFF, 0x7FFF_FFFF, 8)

    #TEST4 random slt
    rng = random.Random(2026)
    for _ in range(100000):
        a = rng.getrandbits(32)
        b = rng.getrandbits(32)

        await check_alu(dut, a, b, 8)


@cocotb.test()
async def test_sltu(dut):
    #TEST1 unsigned less-than: both outcomes, including values with MSB set
    await check_alu(dut, 20, 26, 9)
    await check_alu(dut, 26, 20, 9)
    await check_alu(dut, 0x8000_0001, 0x8000_0002, 9)
    await check_alu(dut, 0x8000_0002, 0x8000_0001, 9)

    #TEST2 equality is false; zero is the smallest unsigned value
    await check_alu(dut, 26, 26, 9)
    await check_alu(dut, 0, 0, 9)
    await check_alu(dut, 0, 1, 9)
    await check_alu(dut, 1, 0, 9)
    await check_alu(dut, 0, 0xFFFF_FFFF, 9)
    await check_alu(dut, 0xFFFF_FFFF, 0, 9)

    #TEST3 unsigned maximum, MSB boundary and full-width result
    await check_alu(dut, 0x7FFF_FFFF, 0x8000_0000, 9)
    await check_alu(dut, 0x8000_0000, 0x7FFF_FFFF, 9)
    await check_alu(dut, 0xFFFF_FFFF, 1, 9)
    await check_alu(dut, 1, 0xFFFF_FFFF, 9)
    await check_alu(dut, 0xFFFF_FFFE, 0xFFFF_FFFF, 9)
    await check_alu(dut, 0xFFFF_FFFF, 0xFFFF_FFFE, 9)
    await check_alu(dut, 0xFFFF_FFFF, 0xFFFF_FFFF, 9)

    #TEST4 random sltu
    rng = random.Random(2026)
    for _ in range(100000):
        a = rng.getrandbits(32)
        b = rng.getrandbits(32)

        await check_alu(dut, a, b, 9)
