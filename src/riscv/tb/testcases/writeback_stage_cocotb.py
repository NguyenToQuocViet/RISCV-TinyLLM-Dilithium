#------------------------------------------------------------------------------
# Module      : writeback_stage_cocotb
# Description : Directed result selection and RF-write qualification checks.
# Author      : Viet Nguyen To Quoc
# Date        : 2026-10-27
#------------------------------------------------------------------------------

import cocotb
from cocotb.triggers import Timer


async def drive_and_check(
    dut, *, ex_result, load_result, wb_src, rd, reg_write,
    instruction_valid, advance_allowed, expected_data, expected_write,
):
    dut.ex_result.value = ex_result
    dut.load_result.value = load_result
    dut.wb_src.value = wb_src
    dut.rd.value = rd
    dut.reg_write.value = reg_write
    dut.instruction_valid.value = instruction_valid
    dut.advance_allowed.value = advance_allowed
    await Timer(1, unit="ns")

    assert int(dut.wb_data.value) == expected_data, (
        f"wb_data: expected 0x{expected_data:08X}, got {dut.wb_data.value}; "
        f"wb_src={wb_src}, valid={instruction_valid}, advance={advance_allowed}"
    )
    assert int(dut.rf_write_fire.value) == expected_write, (
        f"rf_write_fire: expected {expected_write}, got {dut.rf_write_fire.value}; "
        f"valid={instruction_valid}, advance={advance_allowed}, "
        f"reg_write={reg_write}, rd={rd}"
    )


@cocotb.test()
async def test_result_selection(dut):
    # Each row supplies a manual result; the writer remains eligible throughout.
    # ex_result, load_result, wb_src, expected_data
    vectors = [
        (0x80000001, 0x12345678, 0, 0x80000001),
        # Changing only the unselected load input must leave EX data unchanged.
        (0x80000001, 0xDEADBEEF, 0, 0x80000001),
        (0x00000000, 0xDEADBEEF, 0, 0x00000000),
        (0xFFFFFFFF, 0xDEADBEEF, 0, 0xFFFFFFFF),
        # EX has already prepared the jump link; WB only selects it.
        (0x00000024, 0xDEADBEEF, 0, 0x00000024),
        # MEM has already formatted this signed load result.
        (0x00000024, 0xFFFFFF80, 1, 0xFFFFFF80),
        # Changing only the unselected EX input must leave load data unchanged.
        (0x87654321, 0xFFFFFF80, 1, 0xFFFFFF80),
        (0x87654321, 0x00000000, 1, 0x00000000),
        (0x87654321, 0xFFFFFFFF, 1, 0xFFFFFFFF),
        (0x87654321, 0x80000001, 1, 0x80000001),
    ]
    for ex_result, load_result, wb_src, expected_data in vectors:
        await drive_and_check(
            dut, ex_result=ex_result, load_result=load_result, wb_src=wb_src,
            rd=5, reg_write=1, instruction_valid=1, advance_allowed=1,
            expected_data=expected_data, expected_write=1,
        )


@cocotb.test()
async def test_write_qualification(dut):
    # Enumerate all 16 qualification combinations with fixed data.
    # valid, advance, reg_write, rd (zero/nonzero), expected_write
    vectors = [
        (0, 0, 0, 0, 0),
        (0, 0, 0, 5, 0),
        (0, 0, 1, 0, 0),
        (0, 0, 1, 5, 0),
        (0, 1, 0, 0, 0),
        (0, 1, 0, 5, 0),
        (0, 1, 1, 0, 0),
        (0, 1, 1, 5, 0),
        (1, 0, 0, 0, 0),
        (1, 0, 0, 5, 0),
        (1, 0, 1, 0, 0),
        (1, 0, 1, 5, 0),
        (1, 1, 0, 0, 0),
        (1, 1, 0, 5, 0),
        (1, 1, 1, 0, 0),
        (1, 1, 1, 5, 1),
    ]
    for valid, advance, reg_write, rd, expected_write in vectors:
        await drive_and_check(
            dut, ex_result=0x80000001, load_result=0xFFFFFF80, wb_src=0,
            rd=rd, reg_write=reg_write,
            instruction_valid=valid, advance_allowed=advance,
            expected_data=0x80000001, expected_write=expected_write,
        )

    # A load writer to the highest register is also eligible.
    await drive_and_check(
        dut, ex_result=0x80000001, load_result=0xFFFFFF80, wb_src=1,
        rd=31, reg_write=1, instruction_valid=1, advance_allowed=1,
        expected_data=0xFFFFFF80, expected_write=1,
    )
    # Denying advance suppresses the write without clearing selected data.
    await drive_and_check(
        dut, ex_result=0x80000001, load_result=0xFFFFFF80, wb_src=1,
        rd=31, reg_write=1, instruction_valid=1, advance_allowed=0,
        expected_data=0xFFFFFF80, expected_write=0,
    )
    # Restoring permission immediately restores the combinational write output.
    await drive_and_check(
        dut, ex_result=0x80000001, load_result=0xFFFFFF80, wb_src=1,
        rd=31, reg_write=1, instruction_valid=1, advance_allowed=1,
        expected_data=0xFFFFFF80, expected_write=1,
    )
