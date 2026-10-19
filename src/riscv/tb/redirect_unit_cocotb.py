#------------------------------------------------------------------------------
# Module      : redirect_unit_cocotb
# Description : Redirect unit directed tests with explicit expected outputs.
# Author      : Viet Nguyen To Quoc
# Date        : 2026-10-19
#------------------------------------------------------------------------------

import cocotb
from cocotb.triggers import Timer
from ctypes import c_uint32

CF_NONE   = 0b00
CF_BRANCH = 0b01
CF_JAL    = 0b10
CF_JALR   = 0b11


async def check_redirect_unit(
    dut, *,
    alu_result, branch_condition, control_flow,
    instruction_valid, advance_allowed,
    expected_fire, expected_target,
):
    dut.alu_result.value        = c_uint32(alu_result).value
    dut.branch_condition.value  = branch_condition
    dut.control_flow.value      = control_flow
    dut.instruction_valid.value = instruction_valid
    dut.advance_allowed.value   = advance_allowed

    await Timer(1, unit="ns")

    result_fire = int(dut.redirect_fire.value)
    result_target = int(dut.redirect_target.value)
    expected_target = c_uint32(expected_target).value

    assert (result_fire, result_target) == (expected_fire, expected_target), (
        f"flow={control_flow:02b}, condition={branch_condition}, "
        f"valid={instruction_valid}, advance={advance_allowed}, "
        f"alu_result=0x{c_uint32(alu_result).value:08X}: "
        f"expected (fire={expected_fire}, target=0x{expected_target:08X}), "
        f"got (fire={result_fire}, target=0x{result_target:08X})"
    )


@cocotb.test()
async def test_redirect_fire(dut):
    # Every binary control combination; expected columns follow gate_cases.
    gate_cases = (
        (1, 1),
        (0, 1),
        (1, 0),
        (0, 0),
    )
    fire_cases = (
        #flow, condition, expected fire for each (valid, allowed)
        (CF_NONE,   0, (0, 0, 0, 0)),
        (CF_NONE,   1, (0, 0, 0, 0)),
        (CF_BRANCH, 0, (0, 0, 0, 0)),
        (CF_BRANCH, 1, (1, 0, 0, 0)),
        (CF_JAL,    0, (1, 0, 0, 0)),
        (CF_JAL,    1, (1, 0, 0, 0)),
        (CF_JALR,   0, (1, 0, 0, 0)),
        (CF_JALR,   1, (1, 0, 0, 0)),
    )

    for flow, condition, expected_fires in fire_cases:
        for (valid, allowed), expected_fire in zip(gate_cases, expected_fires, strict=True):
            await check_redirect_unit(
                dut,
                alu_result=0x1234_5678,
                branch_condition=condition,
                control_flow=flow,
                instruction_valid=valid,
                advance_allowed=allowed,
                expected_fire=expected_fire,
                expected_target=0x1234_5678,
            )


@cocotb.test()
async def test_target_passthrough(dut):
    target_cases = (
        #ALU result, expected target
        (0x0000_0000, 0x0000_0000),
        (0x0000_0004, 0x0000_0004),
        (0x7FFF_FFFC, 0x7FFF_FFFC),
        (0x8000_0000, 0x8000_0000),
        (0xFFFF_FFFC, 0xFFFF_FFFC),
    )
    flow_cases = (
        #flow, expected fire with condition=valid=allowed=1
        (CF_NONE,   0),
        (CF_BRANCH, 1),
        (CF_JAL,    1),
    )

    for flow, expected_fire in flow_cases:
        for alu_result, expected_target in target_cases:
            await check_redirect_unit(
                dut,
                alu_result=alu_result,
                branch_condition=1,
                control_flow=flow,
                instruction_valid=1,
                advance_allowed=1,
                expected_fire=expected_fire,
                expected_target=expected_target,
            )


@cocotb.test()
async def test_jalr_target(dut):
    # Leaf formatting preserves bit 1; these are not full-core alignment tests.
    target_cases = (
        #ALU result, expected target with only bit 0 cleared
        (0x0000_0000, 0x0000_0000),
        (0x0000_0005, 0x0000_0004),
        (0x7FFF_FFFF, 0x7FFF_FFFE),
        (0x8000_0003, 0x8000_0002),
        (0xFFFF_FFFF, 0xFFFF_FFFE),
    )

    for alu_result, expected_target in target_cases:
        await check_redirect_unit(
            dut,
            alu_result=alu_result,
            branch_condition=0,
            control_flow=CF_JALR,
            instruction_valid=1,
            advance_allowed=1,
            expected_fire=1,
            expected_target=expected_target,
        )


@cocotb.test()
async def test_jalr_target_without_fire(dut):
    # Target formatting remains active when either or both gates are low.
    gate_cases = (
        (0, 1),
        (1, 0),
        (0, 0),
    )
    target_cases = (
        (0x0000_0000, 0x0000_0000),
        (0x0000_0005, 0x0000_0004),
        (0x7FFF_FFFF, 0x7FFF_FFFE),
        (0x8000_0003, 0x8000_0002),
        (0xFFFF_FFFF, 0xFFFF_FFFE),
    )

    for valid, allowed in gate_cases:
        for alu_result, expected_target in target_cases:
            await check_redirect_unit(
                dut,
                alu_result=alu_result,
                branch_condition=0,
                control_flow=CF_JALR,
                instruction_valid=valid,
                advance_allowed=allowed,
                expected_fire=0,
                expected_target=expected_target,
            )


@cocotb.test()
async def test_target_control_transition(dut):
    # Consecutive control changes must restore bit 0 and update fire immediately.
    transition_cases = (
        #flow, expected fire, expected target
        (CF_JALR, 1, 0x8000_0002),
        (CF_JAL,  1, 0x8000_0003),
        (CF_NONE, 0, 0x8000_0003),
    )

    for flow, expected_fire, expected_target in transition_cases:
        await check_redirect_unit(
            dut,
            alu_result=0x8000_0003,
            branch_condition=0,
            control_flow=flow,
            instruction_valid=1,
            advance_allowed=1,
            expected_fire=expected_fire,
            expected_target=expected_target,
        )
