#------------------------------------------------------------------------------
# Module      : result_mux_cocotb
# Description : Directed tests of result_mux (D-RM-01..05).
# Author      : Claude Code (Anthropic)
# Date        : 2026-11-19
#------------------------------------------------------------------------------

from xp_helpers import xp_test, drive, settle, expect

ALU = 0   # RESULT_ALU
LINK = 1  # RESULT_PC_PLUS_4


async def check_result(dut, alu_result, pc_plus_4, result_src, expected):
    drive(dut, alu_result=alu_result, pc_plus_4=pc_plus_4, result_src=result_src)
    await settle()
    expect(dut, result=expected)


@xp_test()
async def test_result_from_alu(dut):
    # D-RM-01: RESULT_ALU selects alu_result
    await check_result(dut, 0x8000_0000, 0x1234_5678, ALU, 0x8000_0000)
    await check_result(dut, 0xFFFF_FFFF, 0x0000_0004, ALU, 0xFFFF_FFFF)
    await check_result(dut, 0x0000_0001, 0xFFFF_FFFC, ALU, 0x0000_0001)


@xp_test()
async def test_result_from_link(dut):
    # D-RM-02: RESULT_PC_PLUS_4 selects pc_plus_4
    await check_result(dut, 0x1234_5678, 0x8000_0000, LINK, 0x8000_0000)
    await check_result(dut, 0x0000_0004, 0xFFFF_FFFF, LINK, 0xFFFF_FFFF)
    await check_result(dut, 0xFFFF_FFFC, 0x0000_0004, LINK, 0x0000_0004)


@xp_test()
async def test_unselected_input_ignored(dut):
    # D-RM-03: the unselected input has no effect
    await check_result(dut, 0xA5A5_A5A5, 0x0000_0000, ALU, 0xA5A5_A5A5)
    await check_result(dut, 0xA5A5_A5A5, 0xFFFF_FFFF, ALU, 0xA5A5_A5A5)
    await check_result(dut, 0x0000_0000, 0xA5A5_A5A5, LINK, 0xA5A5_A5A5)
    await check_result(dut, 0xFFFF_FFFF, 0xA5A5_A5A5, LINK, 0xA5A5_A5A5)


@xp_test()
async def test_selector_change_follows(dut):
    # D-RM-04: output follows the selector alone, never forced to zero
    await check_result(dut, 0x1111_1111, 0x2222_2222, ALU, 0x1111_1111)
    await check_result(dut, 0x1111_1111, 0x2222_2222, LINK, 0x2222_2222)
    await check_result(dut, 0x1111_1111, 0x2222_2222, ALU, 0x1111_1111)
    await check_result(dut, 0x1111_1111, 0x2222_2222, LINK, 0x2222_2222)


@xp_test()
async def test_full_width_data(dut):
    # D-RM-05: every bit of each data input reaches result
    for k in range(32):
        await check_result(dut, 1 << k, 0xFFFF_FFFF, ALU, 1 << k)
    for k in range(32):
        await check_result(dut, 0xFFFF_FFFF, 1 << k, LINK, 1 << k)
