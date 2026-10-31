#------------------------------------------------------------------------------
# Module      : immediate_generator_cocotb
# Description : Directed immediate format and selection checks for the IMM leaf.
# Author      : Viet Nguyen To Quoc
# Date        : 2026-10-31
#------------------------------------------------------------------------------

import cocotb
from cocotb.triggers import Timer


async def check_imm(dut, word, expected):
    # Combinational block (section 2): one drive, 1 ns settle, one check.
    dut.instruction.value = word
    await Timer(1, unit="ns")
    assert int(dut.imm.value) == expected, (
        f"instruction=0x{word:08X}: "
        f"expected imm=0x{expected:08X}, got 0x{int(dut.imm.value):08X}"
    )


@cocotb.test()
async def test_i_format(dut):
    # Section 8 I format, section 5 I equation, section 7 OP-IMM (ADDI) vectors.
    await check_imm(dut, 0x5551_0093, 0x0000_0555)   # addi x1, x2, 1365 (sign 0)
    await check_imm(dut, 0xAAA1_0093, 0xFFFF_FAAA)   # addi x1, x2, -1366 (sign 1)


@cocotb.test()
async def test_s_format(dut):
    # Section 8 S format, section 5 S equation, section 7 STORE (SW) vectors.
    await check_imm(dut, 0x5461_2AA3, 0x0000_0555)   # sw x6, 1365(x2) (sign 0)
    await check_imm(dut, 0xAA61_2523, 0xFFFF_FAAA)   # sw x6, -1366(x2) (sign 1)


@cocotb.test()
async def test_b_format(dut):
    # Section 8 B format, section 5 B equation, section 7 BRANCH (BEQ, BNE) vectors.
    await check_imm(dut, 0x2A20_85E3, 0x0000_0AAA)   # beq x1, x2, +2730 (sign 0)
    await check_imm(dut, 0xD420_9A63, 0xFFFF_F554)   # bne x1, x2, -2732 (sign 1)


@cocotb.test()
async def test_u_format(dut):
    # Section 8 U format, section 5 U equation, section 7 LUI vectors.
    await check_imm(dut, 0x5555_52B7, 0x5555_5000)   # lui x5, 0x55555
    await check_imm(dut, 0xAAAA_A2B7, 0xAAAA_A000)   # lui x5, 0xAAAAA


@cocotb.test()
async def test_j_format(dut):
    # Section 8 J format, section 5 J equation, section 7 JAL vectors.
    await check_imm(dut, 0x2ABA_A0EF, 0x000A_AAAA)   # jal x1, +699050 (sign 0)
    await check_imm(dut, 0xD545_50EF, 0xFFF5_5554)   # jal x1, -699052 (sign 1)


@cocotb.test()
async def test_shift_immediates(dut):
    # Section 8 shifts, section 5 immediate-shift rule: the I equation is unchanged,
    # imm[11:5] is kept and imm[4:0] is the shift amount.
    await check_imm(dut, 0x01F1_1093, 0x0000_001F)   # slli x1, x2, 31 (imm[11:5]=0x00)
    await check_imm(dut, 0x4031_5093, 0x0000_0403)   # srai x1, x2, 3 (imm[11:5]=0x20)


@cocotb.test()
async def test_selection_other_classes(dut):
    # Owner addition 2026-10-31, beyond section 8: section 4 format selection for
    # JALR (I), LOAD (I) and AUIPC (U). Expected values from the section 5 equations.
    await check_imm(dut, 0xAAA1_00E7, 0xFFFF_FAAA)   # jalr x1, -1366(x2): I, sign 1
    await check_imm(dut, 0x5551_2083, 0x0000_0555)   # lw x1, 1365(x2): I, sign 0
    await check_imm(dut, 0xAAAA_A297, 0xAAAA_A000)   # auipc x5, 0xAAAAA: U
