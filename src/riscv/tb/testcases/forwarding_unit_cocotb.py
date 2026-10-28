#------------------------------------------------------------------------------
# Module      : forwarding_unit_cocotb
# Description : Forwarding unit directed tests with explicit expected outputs.
# Author      : Viet Nguyen To Quoc
# Date        : 2026-10-19
#------------------------------------------------------------------------------

import cocotb
from cocotb.triggers import Timer
from ctypes import c_uint32


async def check_forwarding_unit(
    dut, *,
    rs1_id, rs2_id, rs1_value, rs2_value,
    mem_valid, mem_reg_write, mem_wb_src, mem_rd, mem_result,
    wb_valid, wb_reg_write, wb_rd, wb_data,
    expected_rs1, expected_rs2,
):
    dut.rs1_id.value           = rs1_id
    dut.rs2_id.value           = rs2_id
    dut.rs1_value.value        = c_uint32(rs1_value).value
    dut.rs2_value.value        = c_uint32(rs2_value).value

    dut.mem_valid.value        = mem_valid
    dut.mem_reg_write.value    = mem_reg_write
    dut.mem_wb_src.value       = mem_wb_src
    dut.mem_rd.value           = mem_rd
    dut.mem_result.value       = c_uint32(mem_result).value

    dut.wb_valid.value         = wb_valid
    dut.wb_reg_write.value     = wb_reg_write
    dut.wb_rd.value            = wb_rd
    dut.wb_data.value          = c_uint32(wb_data).value

    await Timer(1, unit="ns")

    result_rs1 = int(dut.fwd_rs1.value)
    result_rs2 = int(dut.fwd_rs2.value)
    expected_rs1 = c_uint32(expected_rs1).value
    expected_rs2 = c_uint32(expected_rs2).value

    context = (
        f"rs1=x{rs1_id}, rs2=x{rs2_id}; "
        f"MEM(valid={mem_valid}, write={mem_reg_write}, "
        f"load={mem_wb_src}, rd=x{mem_rd}, "
        f"data=0x{c_uint32(mem_result).value:08X}); "
        f"WB(valid={wb_valid}, write={wb_reg_write}, rd=x{wb_rd}, "
        f"data=0x{c_uint32(wb_data).value:08X}); "
        f"fallback=(0x{c_uint32(rs1_value).value:08X}, "
        f"0x{c_uint32(rs2_value).value:08X})"
    )
    assert (result_rs1, result_rs2) == (expected_rs1, expected_rs2), (
        f"{context}: expected (0x{expected_rs1:08X}, 0x{expected_rs2:08X}), "
        f"got (0x{result_rs1:08X}, 0x{result_rs2:08X})"
    )


@cocotb.test()
async def test_mem_match(dut):
    cases = (
        #rs1, rs2, MEM rd, MEM data, expected rs1, expected rs2
        (1,  7,  1, 0x0000_0000, 0x0000_0000, 0x2222_2222),
        (16, 7, 16, 0x8000_0000, 0x8000_0000, 0x2222_2222),
        (31, 7, 31, 0xFFFF_FFFF, 0xFFFF_FFFF, 0x2222_2222),
        (7,  1,  1, 0x0000_0000, 0x1111_1111, 0x0000_0000),
        (7, 16, 16, 0x8000_0000, 0x1111_1111, 0x8000_0000),
        (7, 31, 31, 0xFFFF_FFFF, 0x1111_1111, 0xFFFF_FFFF),
    )

    for rs1, rs2, rd, data, expected_rs1, expected_rs2 in cases:
        await check_forwarding_unit(
            dut,
            rs1_id=rs1, rs2_id=rs2,
            rs1_value=0x1111_1111, rs2_value=0x2222_2222,
            mem_valid=1, mem_reg_write=1, mem_wb_src=0,
            mem_rd=rd, mem_result=data,
            wb_valid=0, wb_reg_write=1, wb_rd=4, wb_data=0xDDDD_DDDD,
            expected_rs1=expected_rs1, expected_rs2=expected_rs2,
        )


@cocotb.test()
async def test_wb_match(dut):
    cases = (
        #rs1, rs2, WB rd, WB data, expected rs1, expected rs2
        (1,  7,  1, 0x0000_0000, 0x0000_0000, 0x2222_2222),
        (16, 7, 16, 0x8000_0000, 0x8000_0000, 0x2222_2222),
        (31, 7, 31, 0xFFFF_FFFF, 0xFFFF_FFFF, 0x2222_2222),
        (7,  1,  1, 0x0000_0000, 0x1111_1111, 0x0000_0000),
        (7, 16, 16, 0x8000_0000, 0x1111_1111, 0x8000_0000),
        (7, 31, 31, 0xFFFF_FFFF, 0x1111_1111, 0xFFFF_FFFF),
    )

    for rs1, rs2, rd, data, expected_rs1, expected_rs2 in cases:
        await check_forwarding_unit(
            dut,
            rs1_id=rs1, rs2_id=rs2,
            rs1_value=0x1111_1111, rs2_value=0x2222_2222,
            mem_valid=1, mem_reg_write=1, mem_wb_src=0,
            mem_rd=4, mem_result=0xCCCC_CCCC,
            wb_valid=1, wb_reg_write=1, wb_rd=rd, wb_data=data,
            expected_rs1=expected_rs1, expected_rs2=expected_rs2,
        )


@cocotb.test()
async def test_no_match(dut):
    cases = (
        #rs1, rs2, MEM valid, MEM rd, WB valid, WB rd
        # MEM does not match rs1, then rs2; all other producer guards permit forwarding.
        (1,  7, 1,  2, 0, 4),
        (16, 7, 1, 17, 0, 4),
        (31, 7, 1, 30, 0, 4),
        (7,  1, 1,  2, 0, 4),
        (7, 16, 1, 17, 0, 4),
        (7, 31, 1, 30, 0, 4),
        # WB does not match rs1, then rs2.
        (1,  7, 0, 4, 1,  2),
        (16, 7, 0, 4, 1, 17),
        (31, 7, 0, 4, 1, 30),
        (7,  1, 0, 4, 1,  2),
        (7, 16, 0, 4, 1, 17),
        (7, 31, 0, 4, 1, 30),
    )

    for rs1, rs2, mem_valid, mem_rd, wb_valid, wb_rd in cases:
        await check_forwarding_unit(
            dut,
            rs1_id=rs1, rs2_id=rs2,
            rs1_value=0x1111_1111, rs2_value=0x2222_2222,
            mem_valid=mem_valid, mem_reg_write=1, mem_wb_src=0,
            mem_rd=mem_rd, mem_result=0xCCCC_CCCC,
            wb_valid=wb_valid, wb_reg_write=1, wb_rd=wb_rd, wb_data=0xDDDD_DDDD,
            expected_rs1=0x1111_1111, expected_rs2=0x2222_2222,
        )


@cocotb.test()
async def test_mem_priority(dut):
    cases = (
        #rs1, rs2, WB rd, expected rs1, expected rs2
        # Both producers match the selected source: MEM wins over WB.
        (1, 7, 1, 0xCCCC_CCCC, 0x2222_2222),
        (7, 1, 1, 0x1111_1111, 0xCCCC_CCCC),
        # Only MEM matches: MEM wins over the carried register value.
        (1, 7, 2, 0xCCCC_CCCC, 0x2222_2222),
        (7, 1, 2, 0x1111_1111, 0xCCCC_CCCC),
    )

    for rs1, rs2, wb_rd, expected_rs1, expected_rs2 in cases:
        await check_forwarding_unit(
            dut,
            rs1_id=rs1, rs2_id=rs2,
            rs1_value=0x1111_1111, rs2_value=0x2222_2222,
            mem_valid=1, mem_reg_write=1, mem_wb_src=0,
            mem_rd=1, mem_result=0xCCCC_CCCC,
            wb_valid=1, wb_reg_write=1, wb_rd=wb_rd, wb_data=0xDDDD_DDDD,
            expected_rs1=expected_rs1, expected_rs2=expected_rs2,
        )


@cocotb.test()
async def test_zero_destination(dut):
    cases = (
        #MEM rd, WB rd; each producer tries forwarding nonzero data to source x0.
        (0, 31),
        (31, 0),
    )

    for mem_rd, wb_rd in cases:
        await check_forwarding_unit(
            dut,
            rs1_id=0, rs2_id=0,
            rs1_value=0, rs2_value=0,
            mem_valid=1, mem_reg_write=1, mem_wb_src=0,
            mem_rd=mem_rd, mem_result=0xCCCC_CCCC,
            wb_valid=1, wb_reg_write=1, wb_rd=wb_rd, wb_data=0xDDDD_DDDD,
            expected_rs1=0, expected_rs2=0,
        )


@cocotb.test()
async def test_mem_guards(dut):
    guard_cases = (
        #valid, write, load, selected with WB, selected without WB for rs1 / rs2
        (0, 0, 0, 0xDDDD_DDDD, 0x1111_1111, 0x2222_2222),
        (0, 0, 1, 0xDDDD_DDDD, 0x1111_1111, 0x2222_2222),
        (0, 1, 0, 0xDDDD_DDDD, 0x1111_1111, 0x2222_2222),
        (0, 1, 1, 0xDDDD_DDDD, 0x1111_1111, 0x2222_2222),
        (1, 0, 0, 0xDDDD_DDDD, 0x1111_1111, 0x2222_2222),
        (1, 0, 1, 0xDDDD_DDDD, 0x1111_1111, 0x2222_2222),
        (1, 1, 0, 0xCCCC_CCCC, 0xCCCC_CCCC, 0xCCCC_CCCC),
        (1, 1, 1, 0xDDDD_DDDD, 0x1111_1111, 0x2222_2222),
    )

    # A matching MEM load is ineligible here; parent interlock owns safe consumption.
    for valid, write, load, with_wb, without_wb_rs1, without_wb_rs2 in guard_cases:
        source_cases = (
            #rs1, rs2, WB valid, expected rs1, expected rs2
            (1, 7, 1, with_wb,        0x2222_2222),
            (7, 1, 1, 0x1111_1111,    with_wb),
            (1, 7, 0, without_wb_rs1, 0x2222_2222),
            (7, 1, 0, 0x1111_1111,    without_wb_rs2),
        )
        for rs1, rs2, wb_valid, expected_rs1, expected_rs2 in source_cases:
            await check_forwarding_unit(
                dut,
                rs1_id=rs1, rs2_id=rs2,
                rs1_value=0x1111_1111, rs2_value=0x2222_2222,
                mem_valid=valid, mem_reg_write=write, mem_wb_src=load,
                mem_rd=1, mem_result=0xCCCC_CCCC,
                wb_valid=wb_valid, wb_reg_write=1, wb_rd=1, wb_data=0xDDDD_DDDD,
                expected_rs1=expected_rs1, expected_rs2=expected_rs2,
            )


@cocotb.test()
async def test_wb_guards(dut):
    guard_cases = (
        #valid, write, selected rs1 / rs2
        (0, 0, 0x1111_1111, 0x2222_2222),
        (0, 1, 0x1111_1111, 0x2222_2222),
        (1, 0, 0x1111_1111, 0x2222_2222),
        (1, 1, 0xDDDD_DDDD, 0xDDDD_DDDD),
    )

    for valid, write, selected_rs1, selected_rs2 in guard_cases:
        source_cases = (
            (1, 7, selected_rs1, 0x2222_2222),
            (7, 1, 0x1111_1111, selected_rs2),
        )
        for rs1, rs2, expected_rs1, expected_rs2 in source_cases:
            await check_forwarding_unit(
                dut,
                rs1_id=rs1, rs2_id=rs2,
                rs1_value=0x1111_1111, rs2_value=0x2222_2222,
                mem_valid=0, mem_reg_write=1, mem_wb_src=0,
                mem_rd=1, mem_result=0xCCCC_CCCC,
                wb_valid=valid, wb_reg_write=write, wb_rd=1, wb_data=0xDDDD_DDDD,
                expected_rs1=expected_rs1, expected_rs2=expected_rs2,
            )


@cocotb.test()
async def test_simultaneous_sources(dut):
    cases = (
        #rs1, rs2, carried rs2, expected rs1, expected rs2; MEM rd=1, WB rd=2
        (1, 1, 0x1111_1111, 0xCCCC_CCCC, 0xCCCC_CCCC),  #both select MEM
        (2, 2, 0x1111_1111, 0xDDDD_DDDD, 0xDDDD_DDDD),  #both select WB
        (1, 2, 0x2222_2222, 0xCCCC_CCCC, 0xDDDD_DDDD),  #rs1 MEM, rs2 WB
        (2, 1, 0x2222_2222, 0xDDDD_DDDD, 0xCCCC_CCCC),  #rs1 WB, rs2 MEM
    )

    for rs1, rs2, rs2_value, expected_rs1, expected_rs2 in cases:
        await check_forwarding_unit(
            dut,
            rs1_id=rs1, rs2_id=rs2,
            rs1_value=0x1111_1111, rs2_value=rs2_value,
            mem_valid=1, mem_reg_write=1, mem_wb_src=0,
            mem_rd=1, mem_result=0xCCCC_CCCC,
            wb_valid=1, wb_reg_write=1, wb_rd=2, wb_data=0xDDDD_DDDD,
            expected_rs1=expected_rs1, expected_rs2=expected_rs2,
        )


@cocotb.test()
async def test_selection_transition(dut):
    # Keep both IDs matched while eligibility changes: MEM -> WB -> fallback.
    cases = (
        #MEM valid, WB valid, expected rs1, expected rs2
        (1, 1, 0xCCCC_CCCC, 0xCCCC_CCCC),
        (0, 1, 0xDDDD_DDDD, 0xDDDD_DDDD),
        (0, 0, 0x1111_1111, 0x1111_1111),
    )

    for mem_valid, wb_valid, expected_rs1, expected_rs2 in cases:
        await check_forwarding_unit(
            dut,
            rs1_id=1, rs2_id=1,
            rs1_value=0x1111_1111, rs2_value=0x1111_1111,
            mem_valid=mem_valid, mem_reg_write=1, mem_wb_src=0,
            mem_rd=1, mem_result=0xCCCC_CCCC,
            wb_valid=wb_valid, wb_reg_write=1, wb_rd=1, wb_data=0xDDDD_DDDD,
            expected_rs1=expected_rs1, expected_rs2=expected_rs2,
        )
