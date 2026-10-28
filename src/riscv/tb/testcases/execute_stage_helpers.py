#------------------------------------------------------------------------------
# Module      : execute_stage_helpers
# Description : Explicit EX stimulus and checking helpers; no result model.
# Author      : OpenAI Codex
# Date        : 2026-10-19
#------------------------------------------------------------------------------

from ctypes import c_uint32
from cocotb.triggers import Timer

ALU_ADD, ALU_SUB, ALU_AND, ALU_OR, ALU_XOR = range(5)
ALU_SLL, ALU_SRL, ALU_SRA, ALU_SLT, ALU_SLTU = range(5, 10)
ALU_A_RS1, ALU_A_PC, ALU_A_ZERO = 0, 1, 2
ALU_B_RS2, ALU_B_IMM = 0, 1
RESULT_ALU, RESULT_PC_PLUS_4 = 0, 1
CF_NONE, CF_BRANCH, CF_JAL, CF_JALR = 0, 1, 2, 3
BR_EQ, BR_NE, BR_LT_SIGNED, BR_GE_SIGNED = 0, 1, 4, 5
BR_LT_UNSIGNED, BR_GE_UNSIGNED = 6, 7


def ex_inputs(**changes):
    # Each vector starts independently; disabled producers carry distinct poison data.
    inputs = dict(
        pc=0x1000, imm=0,
        rs1_id=1, rs2_id=2, rs1_value=0, rs2_value=0,
        alu_src_a=ALU_A_RS1, alu_src_b=ALU_B_RS2, alu_op=ALU_ADD,
        branch_kind=BR_EQ, control_flow=CF_NONE, result_src=RESULT_ALU,
        instruction_valid=1, advance_allowed=1,
        mem_rd=1, mem_result=0xCCCC_CCCC,
        mem_valid=0, mem_reg_write=1, mem_wb_src=0,
        wb_rd=2, wb_data=0xDDDD_DDDD, wb_valid=0, wb_reg_write=1,
    )
    assert changes.keys() <= inputs.keys(), f"Unknown EX inputs: {changes.keys() - inputs.keys()}"
    inputs.update(changes)
    return inputs


def check_control(inputs, *, uses_alu=True, uses_operand_a=True):
    # Testbench diagnostics, qualified by semantic use rather than advance permission.
    if not inputs["instruction_valid"]:
        return
    if uses_alu:
        assert inputs["alu_op"] in range(10), "Live instruction has reserved alu_op"
    if uses_operand_a:
        assert inputs["alu_src_a"] in (ALU_A_RS1, ALU_A_PC, ALU_A_ZERO), (
            "Live instruction has reserved alu_src_a"
        )
    if inputs["control_flow"] == CF_BRANCH:
        assert inputs["branch_kind"] in (0, 1, 4, 5, 6, 7), (
            "Live conditional branch has reserved branch_kind"
        )


def drive_execute_stage(dut, inputs):
    for name, value in inputs.items():
        getattr(dut, name).value = c_uint32(value).value


def assert_ex_outputs(dut, *, name, expected_result, expected_store, expected_fire, expected_target):
    expected = dict(
        ex_result=expected_result, store_data=expected_store,
        redirect_fire=expected_fire, redirect_target=expected_target,
    )
    for port, value in expected.items():
        # None is only for an architecturally unused datapath output.
        if value is not None:
            actual = int(getattr(dut, port).value)
            value = c_uint32(value).value
            assert actual == value, (
                f"{name}: {port} expected 0x{value:08X}, got 0x{actual:08X}"
            )


async def check_execute_stage(
    dut, *, name, inputs,
    expected_result, expected_store, expected_fire, expected_target,
    uses_alu=True, uses_operand_a=True,
):
    check_control(inputs, uses_alu=uses_alu, uses_operand_a=uses_operand_a)
    drive_execute_stage(dut, inputs)
    await Timer(1, unit="ns")
    assert_ex_outputs(
        dut, name=name, expected_result=expected_result, expected_store=expected_store,
        expected_fire=expected_fire, expected_target=expected_target,
    )
