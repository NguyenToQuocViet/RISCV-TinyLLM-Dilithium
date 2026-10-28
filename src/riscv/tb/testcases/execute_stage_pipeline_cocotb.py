#------------------------------------------------------------------------------
# Module      : execute_stage_pipeline_cocotb
# Description : Directed EX capture, hold and release tests in a minimal harness.
# Author      : OpenAI Codex
# Date        : 2026-10-19
#------------------------------------------------------------------------------

import cocotb
from cocotb.triggers import Timer
from ctypes import c_uint32

from execute_stage_helpers import (
    ALU_A_PC, ALU_B_IMM, RESULT_PC_PLUS_4,
    CF_BRANCH, CF_JAL, CF_JALR,
    ex_inputs, check_control, drive_execute_stage, assert_ex_outputs,
)


async def tick(dut, *, expected_fire=0):
    # Observe the pre-edge event, then let sequential updates settle before checking capture.
    dut.clk.value = 0
    await Timer(1, unit="ns")
    fire = int(dut.redirect_fire.value)
    assert fire == expected_fire, f"Pre-edge redirect expected {expected_fire}, got {fire}"
    dut.clk.value = 1
    await Timer(1, unit="ns")
    dut.clk.value = 0
    await Timer(1, unit="ns")
    return fire


async def reset_harness(dut):
    drive_execute_stage(dut, ex_inputs(instruction_valid=0))
    dut.clk.value = 0
    dut.rst_n.value = 0
    dut.hold.value = 0
    dut.flush_ex.value = 0
    dut.load_ex.value = 0
    dut.instruction_tag.value = 0
    dut.instruction_rd.value = 0
    dut.instruction_reg_write.value = 0
    dut.instruction_mem_en.value = 0
    dut.instruction_mem_write.value = 0
    await tick(dut)
    assert int(dut.current_valid.value) == 0
    assert int(dut.captured_valid.value) == 0
    dut.rst_n.value = 1
    await Timer(1, unit="ns")


async def load_instruction(
    dut, *, inputs, tag, rd=0, reg_write=0, mem_en=0, mem_write=0,
    expected_previous_fire=0,
):
    check_control(inputs)
    drive_execute_stage(dut, inputs)
    dut.instruction_tag.value = tag
    dut.instruction_rd.value = rd
    dut.instruction_reg_write.value = reg_write
    dut.instruction_mem_en.value = mem_en
    dut.instruction_mem_write.value = mem_write
    dut.load_ex.value = 1
    await tick(dut, expected_fire=expected_previous_fire)
    dut.load_ex.value = 0
    assert int(dut.current_valid.value) == inputs["instruction_valid"]
    assert int(dut.current_tag.value) == tag


def check_capture(dut, *, name, valid, tag=None, rd=None, reg_write=None,
                  mem_en=None, mem_write=None, result=None, store=None):
    assert int(dut.captured_valid.value) == valid, f"{name}: captured valid"
    fields = dict(
        captured_tag=tag, captured_rd=rd, captured_reg_write=reg_write,
        captured_mem_en=mem_en, captured_mem_write=mem_write,
        captured_result=result, captured_store_data=store,
    )
    for port, value in fields.items():
        if value is not None:
            actual = int(getattr(dut, port).value)
            assert actual == c_uint32(value).value, (
                f"{name}: {port} expected 0x{c_uint32(value).value:08X}, got 0x{actual:08X}"
            )


@cocotb.test()
async def test_normal_capture_and_metadata(dut):
    await reset_harness(dut)
    await load_instruction(
        dut, inputs=ex_inputs(rs1_value=2, rs2_value=3),
        tag=11, rd=5, reg_write=1,
    )
    check_capture(dut, name="Initial bubble", valid=0)
    await load_instruction(
        dut, inputs=ex_inputs(rs1_value=0x10020, rs2_value=0xAABB_CCDD,
                             imm=-16, alu_src_b=ALU_B_IMM),
        tag=22, rd=0, reg_write=0, mem_en=1, mem_write=1,
    )
    check_capture(dut, name="Arithmetic metadata", valid=1, tag=11, rd=5,
                  reg_write=1, mem_en=0, mem_write=0, result=5, store=3)
    await tick(dut)
    check_capture(dut, name="Store metadata", valid=1, tag=22, rd=0,
                  reg_write=0, mem_en=1, mem_write=1,
                  result=0x10010, store=0xAABB_CCDD)
    await tick(dut)
    check_capture(dut, name="Drained bubble", valid=0)


@cocotb.test()
async def test_redirect_hold_and_release(dut):
    cases = (
        #flow, source A, immediate, base, result selector, expected result, target, store
        (CF_BRANCH, ALU_A_PC, -16, 7, 0, 0x0FF0, 0x0FF0, 7),
        (CF_JAL, ALU_A_PC, 32, 7, RESULT_PC_PLUS_4, 0x1004, 0x1020, 7),
        (CF_JALR, 0, 4, 0x3001, RESULT_PC_PLUS_4, 0x1004, 0x3004, 7),
    )
    for flow, source, imm, base, selector, result, target, store in cases:
        await reset_harness(dut)
        await load_instruction(
            dut, inputs=ex_inputs(rs1_value=0x70, rs2_value=7),
            tag=99, rd=9, reg_write=1,
        )
        await load_instruction(
            dut, inputs=ex_inputs(pc=0x1000, imm=imm, alu_src_a=source,
                                 alu_src_b=ALU_B_IMM, result_src=selector, control_flow=flow,
                                 rs1_value=0xBAD0, rs2_value=8,
                                 mem_valid=1, mem_rd=1, mem_result=base,
                                 wb_valid=1, wb_rd=2, wb_data=7),
            tag=100 + flow, rd=1, reg_write=int(flow != CF_BRANCH),
        )
        dut.hold.value = 1
        # Incoming WB data changes, but held registered WB must remain available to EX.
        dut.wb_data.value = 99
        for cycle in range(3):
            await tick(dut)
            assert int(dut.current_valid.value) == 1
            assert int(dut.current_tag.value) == 100 + flow
            assert_ex_outputs(
                dut, name=f"Held flow {flow}, cycle {cycle}", expected_result=result,
                expected_store=store, expected_fire=0, expected_target=target,
            )
            check_capture(dut, name="Held previous entry", valid=1, tag=99, rd=9,
                          reg_write=1, mem_en=0, mem_write=0, result=0x77, store=7)
        dut.hold.value = 0
        events = await tick(dut, expected_fire=1)
        check_capture(dut, name="Redirect release", valid=1, tag=100 + flow, rd=1,
                      reg_write=int(flow != CF_BRANCH), mem_en=0, mem_write=0,
                      result=result, store=store)
        assert int(dut.current_valid.value) == 0
        events += await tick(dut)
        events += await tick(dut)
        assert events == 1, "One held instruction must produce one redirect on release"
        check_capture(dut, name="No duplicate capture", valid=0)


@cocotb.test()
async def test_wb_forwarding_release_edge(dut):
    await reset_harness(dut)
    await load_instruction(
        dut, inputs=ex_inputs(rs1_value=2, rs2_value=3,
                             wb_valid=1, wb_rd=1, wb_data=20),
        tag=31, rd=6, reg_write=1,
    )
    dut.hold.value = 1
    dut.wb_valid.value = 0
    dut.wb_data.value = 0xBAD0
    for _ in range(3):
        await tick(dut)
        assert_ex_outputs(dut, name="Held WB forwarding", expected_result=23,
                          expected_store=3, expected_fire=0, expected_target=23)
    dut.hold.value = 0
    await tick(dut)
    check_capture(dut, name="WB value on release", valid=1, tag=31, rd=6,
                  reg_write=1, mem_en=0, mem_write=0, result=23, store=3)


@cocotb.test()
async def test_load_unavailable_then_wb(dut):
    await reset_harness(dut)
    # The load-use bubble is supplied externally; EX must not consume the load address.
    await load_instruction(
        dut, inputs=ex_inputs(instruction_valid=0, rs1_value=2, rs2_value=3, mem_valid=1,
                             mem_wb_src=1, mem_rd=1, mem_result=0x10000,
                             wb_valid=1, wb_rd=1, wb_data=20),
        tag=41, rd=7, reg_write=1,
    )
    dut.hold.value = 1
    for _ in range(3):
        await tick(dut)
        assert_ex_outputs(dut, name="MEM load never forwarded", expected_result=23,
                          expected_store=3, expected_fire=0, expected_target=23)
        check_capture(dut, name="Dependent result not consumed", valid=0)
    # At the modeled response edge the existing bubble leaves EX, the dependent
    # instruction enters EX, and the formatted load result enters registered WB.
    dut.hold.value = 0
    await load_instruction(
        dut, inputs=ex_inputs(rs1_value=2, rs2_value=3, wb_valid=1, wb_rd=1, wb_data=50),
        tag=42, rd=7, reg_write=1,
    )
    check_capture(dut, name="Response edge does not consume stale data", valid=0)
    assert_ex_outputs(dut, name="Completed load from WB", expected_result=53,
                      expected_store=3, expected_fire=0, expected_target=53)
    await tick(dut)
    check_capture(dut, name="Consume WB load result", valid=1, tag=42, rd=7,
                  reg_write=1, mem_en=0, mem_write=0, result=53, store=3)


@cocotb.test()
async def test_bubble_and_flush(dut):
    await reset_harness(dut)
    await load_instruction(
        dut, inputs=ex_inputs(instruction_valid=0, imm=32, alu_src_a=ALU_A_PC,
                             alu_src_b=ALU_B_IMM, control_flow=CF_JAL,
                             result_src=RESULT_PC_PLUS_4),
        tag=51, rd=1, reg_write=1,
    )
    await tick(dut)
    check_capture(dut, name="Bubble cannot capture live entry", valid=0)
    await load_instruction(
        dut, inputs=ex_inputs(imm=32, alu_src_a=ALU_A_PC, alu_src_b=ALU_B_IMM,
                             control_flow=CF_JAL, result_src=RESULT_PC_PLUS_4),
        tag=52, rd=1, reg_write=1,
    )
    dut.flush_ex.value = 1
    await tick(dut)
    assert int(dut.current_valid.value) == 0
    check_capture(dut, name="Explicit EX kill", valid=0)
    dut.flush_ex.value = 0
    await tick(dut)


@cocotb.test()
async def test_reset_during_hold_and_recovery(dut):
    await reset_harness(dut)
    await load_instruction(
        dut, inputs=ex_inputs(rs1_value=2, rs2_value=3), tag=60, rd=5, reg_write=1,
    )
    await load_instruction(
        dut, inputs=ex_inputs(imm=32, alu_src_a=ALU_A_PC, alu_src_b=ALU_B_IMM,
                             control_flow=CF_JAL, result_src=RESULT_PC_PLUS_4),
        tag=61, rd=1, reg_write=1,
    )
    check_capture(dut, name="Occupied output before reset", valid=1, tag=60, rd=5,
                  reg_write=1, mem_en=0, mem_write=0, result=5, store=3)
    dut.hold.value = 1
    await tick(dut)
    dut.rst_n.value = 0
    await tick(dut)
    assert int(dut.current_valid.value) == 0
    check_capture(dut, name="Reset overrides hold", valid=0)
    dut.rst_n.value = 1
    dut.hold.value = 0
    await tick(dut)
    await load_instruction(
        dut, inputs=ex_inputs(rs1_value=4, rs2_value=5), tag=62, rd=8, reg_write=1,
    )
    await tick(dut)
    check_capture(dut, name="Post-reset new instruction", valid=1, tag=62, rd=8,
                  reg_write=1, mem_en=0, mem_write=0, result=9, store=5)
