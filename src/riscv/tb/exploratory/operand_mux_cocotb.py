#------------------------------------------------------------------------------
# Module      : operand_mux_cocotb
# Description : Directed tests of operand_mux (D-OM-01..08).
# Author      : Claude Code (Anthropic)
# Date        : 2026-11-19
#------------------------------------------------------------------------------

from xp_helpers import xp_test, drive, settle, expect

A_RS1, A_PC, A_ZERO, A_UNUSED = 0b00, 0b01, 0b10, 0b11  # alu_src_a codes
B_RS2, B_IMM = 0, 1                                      # alu_src_b codes


async def check_operands(dut, rs1_value, rs2_value, pc, imm, alu_src_a, alu_src_b, **expected):
    drive(dut, rs1_value=rs1_value, rs2_value=rs2_value, pc=pc, imm=imm,
          alu_src_a=alu_src_a, alu_src_b=alu_src_b)
    await settle()
    expect(dut, **expected)


@xp_test()
async def test_operand_a_register(dut):
    # D-OM-01: ALU_A_RS1 gives rs1_value
    await check_operands(dut, 0x1111_1111, 0x2222_2222, 0x3333_3333, 0x4444_4444, A_RS1, B_RS2,
                         operand_a=0x1111_1111)


@xp_test()
async def test_operand_a_pc(dut):
    # D-OM-02: ALU_A_PC gives pc, 32 bits
    await check_operands(dut, 0x1111_1111, 0, 0x8000_0000, 0, A_PC, B_RS2, operand_a=0x8000_0000)
    await check_operands(dut, 0x1111_1111, 0, 0xFFFF_FFFF, 0, A_PC, B_RS2, operand_a=0xFFFF_FFFF)
    await check_operands(dut, 0x1111_1111, 0, 0x0000_0004, 0, A_PC, B_RS2, operand_a=0x0000_0004)


@xp_test()
async def test_operand_a_zero(dut):
    # D-OM-03: ALU_A_ZERO is a constant zero
    await check_operands(dut, 0xFFFF_FFFF, 0, 0xFFFF_FFFF, 0xFFFF_FFFF, A_ZERO, B_RS2,
                         operand_a=0x0000_0000)


@xp_test()
async def test_operand_a_fallback(dut):
    # D-OM-04: unassigned code 2'b11 gives the diagnostic value (OM-D1)
    await check_operands(dut, 0, 0, 0, 0, A_UNUSED, B_RS2, operand_a=0xDEAD_BEEF)
    await check_operands(dut, 0xFFFF_FFFF, 0, 0xFFFF_FFFF, 0xFFFF_FFFF, A_UNUSED, B_RS2,
                         operand_a=0xDEAD_BEEF)


@xp_test()
async def test_operand_b_register(dut):
    # D-OM-05: ALU_B_RS2 gives rs2_value
    await check_operands(dut, 0x1111_1111, 0x2222_2222, 0x3333_3333, 0x4444_4444, A_RS1, B_RS2,
                         operand_b=0x2222_2222)


@xp_test()
async def test_operand_b_immediate(dut):
    # D-OM-06: ALU_B_IMM gives imm, 32 bits
    await check_operands(dut, 0, 0x2222_2222, 0, 0x8000_0000, A_RS1, B_IMM, operand_b=0x8000_0000)
    await check_operands(dut, 0, 0x2222_2222, 0, 0xFFFF_FFFF, A_RS1, B_IMM, operand_b=0xFFFF_FFFF)


@xp_test()
async def test_independent_selection(dut):
    # D-OM-07: each output follows its own selector alone, 8 combinations
    operand_a = {A_RS1: 0x1111_1111, A_PC: 0x3333_3333, A_ZERO: 0x0000_0000, A_UNUSED: 0xDEAD_BEEF}
    operand_b = {B_RS2: 0x2222_2222, B_IMM: 0x4444_4444}
    for a in (A_RS1, A_PC, A_ZERO, A_UNUSED):
        for b in (B_RS2, B_IMM):
            await check_operands(dut, 0x1111_1111, 0x2222_2222, 0x3333_3333, 0x4444_4444, a, b,
                                 operand_a=operand_a[a], operand_b=operand_b[b])


@xp_test()
async def test_full_width_data(dut):
    # D-OM-08: every bit of each data input reaches its output
    ones = 0xFFFF_FFFF
    for k in range(32):
        await check_operands(dut, 1 << k, ones, ones, ones, A_RS1, B_RS2, operand_a=1 << k)
        await check_operands(dut, ones, ones, 1 << k, ones, A_PC, B_RS2, operand_a=1 << k)
        await check_operands(dut, ones, 1 << k, ones, ones, A_RS1, B_RS2, operand_b=1 << k)
        await check_operands(dut, ones, ones, ones, 1 << k, A_RS1, B_IMM, operand_b=1 << k)
