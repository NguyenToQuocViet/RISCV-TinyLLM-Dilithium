#------------------------------------------------------------------------------
# Module      : execute_stage_cocotb
# Description : Directed EX composition tests with manually specified expected data.
# Author      : OpenAI Codex
# Date        : 2026-10-19
#------------------------------------------------------------------------------

import cocotb

from execute_stage_helpers import (
    ALU_ADD, ALU_SUB, ALU_AND, ALU_OR, ALU_XOR,
    ALU_SLL, ALU_SRL, ALU_SRA, ALU_SLT, ALU_SLTU,
    ALU_A_RS1, ALU_A_PC, ALU_A_ZERO, ALU_B_RS2, ALU_B_IMM,
    RESULT_ALU, RESULT_PC_PLUS_4,
    CF_NONE, CF_BRANCH, CF_JAL, CF_JALR,
    BR_EQ, BR_NE, BR_LT_SIGNED, BR_GE_SIGNED, BR_LT_UNSIGNED, BR_GE_UNSIGNED,
    ex_inputs, check_control, check_execute_stage,
)


@cocotb.test()
async def test_register_operations(dut):
    cases = (
        #name, operation, A, B, expected result
        ("ADD", ALU_ADD, 2, 3, 5),
        ("SUB", ALU_SUB, 2, 3, 0xFFFF_FFFF),
        ("AND", ALU_AND, 0xF0F0_00FF, 0x0FF0_0F0F, 0x00F0_000F),
        ("OR", ALU_OR, 0xF000_00F0, 0x0F00_000F, 0xFF00_00FF),
        ("XOR", ALU_XOR, 0xAAAA_AAAA, 0xFFFF_0000, 0x5555_AAAA),
        ("SLL", ALU_SLL, 1, 31, 0x8000_0000),
        ("SRL", ALU_SRL, 0x8000_0000, 31, 1),
        ("SRA", ALU_SRA, 0x8000_0000, 31, 0xFFFF_FFFF),
        ("SLT", ALU_SLT, 0xFFFF_FFFF, 0, 1),
        ("SLTU", ALU_SLTU, 0xFFFF_FFFF, 0, 0),
        ("ADD wrap", ALU_ADD, 0xFFFF_FFFF, 1, 0),
        ("ADD signed boundary", ALU_ADD, 0x7FFF_FFFF, 1, 0x8000_0000),
        ("SUB wrap", ALU_SUB, 0, 1, 0xFFFF_FFFF),
        ("SLL upper shift bits", ALU_SLL, 1, 0xFFFF_FFE0, 1),
        ("SRL zero shift", ALU_SRL, 0x8000_0001, 0, 0x8000_0001),
    )
    for name, op, a, b, expected in cases:
        await check_execute_stage(
            dut, name=name,
            inputs=ex_inputs(rs1_value=a, rs2_value=b, imm=0x1357, alu_op=op),
            expected_result=expected, expected_store=b,
            expected_fire=0, expected_target=expected,
        )


@cocotb.test()
async def test_immediate_operations(dut):
    cases = (
        ("ADDI", ALU_ADD, 2, -3, 0xFFFF_FFFF),
        ("ANDI", ALU_AND, 0x1234_5678, -16, 0x1234_5670),
        ("ORI", ALU_OR, 0x1234_5600, 0x78, 0x1234_5678),
        ("XORI", ALU_XOR, 0x1234_5678, -1, 0xEDCB_A987),
        ("SLLI", ALU_SLL, 1, 31, 0x8000_0000),
        ("SRLI", ALU_SRL, 0x8000_0000, 31, 1),
        ("SRAI", ALU_SRA, 0x8000_0000, 31, 0xFFFF_FFFF),
        ("SLTI", ALU_SLT, 0xFFFF_FFFF, 0, 1),
        ("SLTIU sign-extended immediate", ALU_SLTU, 1, -1, 1),
    )
    for name, op, a, imm, expected in cases:
        await check_execute_stage(
            dut, name=name,
            inputs=ex_inputs(rs1_value=a, rs2_value=0x55, imm=imm,
                             alu_src_b=ALU_B_IMM, alu_op=op),
            expected_result=expected, expected_store=0x55,
            expected_fire=0, expected_target=expected,
        )


@cocotb.test()
async def test_upper_immediates(dut):
    cases = (
        #name, source A, PC, canonical immediate, expected result
        ("LUI", ALU_A_ZERO, 0x1000, 0x1234_5000, 0x1234_5000),
        ("LUI upper sign bit", ALU_A_ZERO, 0x1000, 0x8000_0000, 0x8000_0000),
        ("AUIPC", ALU_A_PC, 0x1000, 0x2000, 0x3000),
        ("AUIPC negative", ALU_A_PC, 0x3000, -4096, 0x2000),
        ("AUIPC wrap", ALU_A_PC, 0xFFFF_F000, 0x2000, 0x1000),
    )
    for name, source, pc, imm, expected in cases:
        await check_execute_stage(
            dut, name=name,
            inputs=ex_inputs(pc=pc, imm=imm, alu_src_a=source, alu_src_b=ALU_B_IMM,
                             rs1_value=0x77, rs2_value=0x88,
                             mem_valid=1, mem_rd=1, mem_result=0x1111,
                             wb_valid=1, wb_rd=2, wb_data=0x2222),
            expected_result=expected, expected_store=0x2222,
            expected_fire=0, expected_target=expected,
        )


@cocotb.test()
async def test_memory_address_and_store_data(dut):
    # Width/sign formatting belongs to MEM; all eight instructions share this EX path.
    cases = (
        ("LB", 0x10020, -1, 0x1001F),
        ("LH", 0x10020, -2, 0x1001E),
        ("LW", 0x10020, -4, 0x1001C),
        ("LBU", 0x10020, 1, 0x10021),
        ("LHU", 0x10020, 2, 0x10022),
        ("SB", 0x10020, 3, 0x10023),
        ("SH", 0x10020, 2, 0x10022),
        ("SW", 0x10020, -16, 0x10010),
    )
    for name, base, imm, expected in cases:
        await check_execute_stage(
            dut, name=name,
            inputs=ex_inputs(imm=imm, alu_src_b=ALU_B_IMM,
                             rs1_value=0xBAD0, rs2_value=0xBAD1,
                             mem_valid=1, mem_rd=1, mem_result=base,
                             wb_valid=1, wb_rd=2, wb_data=0xA5A5_5A5A),
            expected_result=expected, expected_store=0xA5A5_5A5A,
            expected_fire=0, expected_target=expected,
        )
    for data in (0, 0x8000_0000, 0xFFFF_FFFF):
        await check_execute_stage(
            dut, name="Store data independent of address",
            inputs=ex_inputs(rs1_value=0x10020, imm=-16, alu_src_b=ALU_B_IMM,
                             wb_valid=1, wb_data=data),
            expected_result=0x10010, expected_store=data,
            expected_fire=0, expected_target=0x10010,
        )


@cocotb.test()
async def test_conditional_branches(dut):
    cases = (
        #name, kind, forwarded rs1, forwarded rs2, expected fire
        ("BEQ taken", BR_EQ, 7, 7, 1),
        ("BEQ not taken", BR_EQ, 7, 8, 0),
        ("BNE taken", BR_NE, 7, 8, 1),
        ("BNE not taken", BR_NE, 7, 7, 0),
        ("BLT taken", BR_LT_SIGNED, 0x8000_0000, 0x7FFF_FFFF, 1),
        ("BLT not taken", BR_LT_SIGNED, 0x7FFF_FFFF, 0x8000_0000, 0),
        ("BGE taken", BR_GE_SIGNED, 0x7FFF_FFFF, 0x8000_0000, 1),
        ("BGE not taken", BR_GE_SIGNED, 0x8000_0000, 0x7FFF_FFFF, 0),
        ("BLTU taken", BR_LT_UNSIGNED, 0x7FFF_FFFF, 0x8000_0000, 1),
        ("BLTU not taken", BR_LT_UNSIGNED, 0x8000_0000, 0x7FFF_FFFF, 0),
        ("BGEU taken", BR_GE_UNSIGNED, 0x8000_0000, 0x7FFF_FFFF, 1),
        ("BGEU not taken", BR_GE_UNSIGNED, 0x7FFF_FFFF, 0x8000_0000, 0),
        ("BGE equality", BR_GE_SIGNED, 0, 0, 1),
        ("BGEU equality", BR_GE_UNSIGNED, 0, 0, 1),
    )
    for name, kind, a, b, fire in cases:
        # Both branch operands forwarded; target still comes from PC and immediate.
        await check_execute_stage(
            dut, name=name,
            inputs=ex_inputs(pc=0x1000, imm=-16, alu_src_a=ALU_A_PC,
                             alu_src_b=ALU_B_IMM, control_flow=CF_BRANCH, branch_kind=kind,
                             rs1_value=0x1111, rs2_value=0x2222,
                             mem_valid=1, mem_rd=1, mem_result=a,
                             wb_valid=1, wb_rd=2, wb_data=b),
            expected_result=0x0FF0, expected_store=b,
            expected_fire=fire, expected_target=0x0FF0,
        )
    await check_execute_stage(
        dut, name="Forward branch target and carried equal registers",
        inputs=ex_inputs(pc=0x1000, imm=32, alu_src_a=ALU_A_PC,
                         alu_src_b=ALU_B_IMM, control_flow=CF_BRANCH,
                         rs1_value=5, rs2_value=5),
        expected_result=0x1020, expected_store=5, expected_fire=1, expected_target=0x1020,
    )


@cocotb.test()
async def test_jump_target_and_link(dut):
    cases = (
        #name, flow, source A, PC, immediate, base, expected link, expected target
        ("JAL forward", CF_JAL, ALU_A_PC, 0x1000, 32, 0xBAD0, 0x1004, 0x1020),
        ("JAL backward", CF_JAL, ALU_A_PC, 0x1000, -16, 0xBAD0, 0x1004, 0x0FF0),
        ("JAL PC wrap", CF_JAL, ALU_A_PC, 0xFFFF_FFFC, 4, 0xBAD0, 0, 0),
        ("JALR odd base", CF_JALR, ALU_A_RS1, 0x2000, 4, 0x3001, 0x2004, 0x3004),
        ("JALR negative offset", CF_JALR, ALU_A_RS1, 0x2000, -16, 0x3011, 0x2004, 0x3000),
        ("JALR address wrap", CF_JALR, ALU_A_RS1, 0x2000, 1, 0xFFFF_FFFF, 0x2004, 0),
    )
    for name, flow, source, pc, imm, base, link, target in cases:
        for producer in ("MEM", "WB"):
            await check_execute_stage(
                dut, name=f"{name}, base from {producer}",
                inputs=ex_inputs(pc=pc, imm=imm, alu_src_a=source, alu_src_b=ALU_B_IMM,
                                 control_flow=flow, result_src=RESULT_PC_PLUS_4,
                                 rs1_value=0xDEAD_0000, rs2_value=0x66,
                                 mem_valid=int(producer == "MEM"), mem_rd=1, mem_result=base,
                                 wb_valid=int(producer == "WB"), wb_rd=1, wb_data=base),
                expected_result=link, expected_store=0x66,
                expected_fire=1, expected_target=target,
            )


@cocotb.test()
async def test_forwarding_composition(dut):
    cases = (
        #name, changed inputs, expected result, expected store
        ("MEM rs1", dict(mem_valid=1, mem_rd=1, mem_result=10), 13, 3),
        ("MEM rs2", dict(mem_valid=1, mem_rd=2, mem_result=10), 12, 10),
        ("WB rs1", dict(wb_valid=1, wb_rd=1, wb_data=20), 23, 3),
        ("WB rs2", dict(wb_valid=1, wb_rd=2, wb_data=20), 22, 20),
        ("MEM over WB rs1", dict(mem_valid=1, mem_rd=1, mem_result=10,
                                 wb_valid=1, wb_rd=1, wb_data=20), 13, 3),
        ("MEM over WB rs2", dict(mem_valid=1, mem_rd=2, mem_result=10,
                                 wb_valid=1, wb_rd=2, wb_data=20), 12, 10),
        ("Split producers", dict(mem_valid=1, mem_rd=2, mem_result=10,
                                 wb_valid=1, wb_rd=1, wb_data=20), 30, 10),
        ("Both sources same MEM", dict(rs2_id=1, rs2_value=2,
                                       mem_valid=1, mem_rd=1, mem_result=10), 20, 10),
        ("MEM nonwriter to WB", dict(mem_valid=1, mem_reg_write=0, mem_rd=1,
                                     wb_valid=1, wb_rd=1, wb_data=20), 23, 3),
        ("MEM invalid to WB", dict(mem_valid=0, mem_rd=1,
                                   wb_valid=1, wb_rd=1, wb_data=20), 23, 3),
        ("WB nonwriter", dict(wb_valid=1, wb_reg_write=0, wb_rd=1), 5, 3),
        ("Both producer rd zero", dict(mem_valid=1, mem_rd=0,
                                       wb_valid=1, wb_rd=0), 5, 3),
        ("Consumer x0", dict(rs1_id=0, rs1_value=0, mem_valid=1, mem_rd=0,
                             wb_valid=1, wb_rd=0), 3, 3),
    )
    for name, changes, result, store in cases:
        inputs = ex_inputs(rs1_value=2, rs2_value=3)
        inputs.update(changes)
        await check_execute_stage(
            dut, name=name, inputs=inputs,
            expected_result=result, expected_store=store,
            expected_fire=0, expected_target=result,
        )
    # A matching MEM load is unavailable. Observe fallback while held, never consume it.
    for wb_valid, expected in ((0, 5), (1, 23)):
        await check_execute_stage(
            dut, name="Unavailable MEM load while consumer held",
            inputs=ex_inputs(rs1_value=2, rs2_value=3, advance_allowed=0,
                             mem_valid=1, mem_wb_from_mem=1, mem_result=0x10000,
                             wb_valid=wb_valid, wb_rd=1, wb_data=20),
            expected_result=expected, expected_store=3,
            expected_fire=0, expected_target=expected,
        )


@cocotb.test()
async def test_forwarding_to_address_paths(dut):
    for producer in ("MEM", "WB"):
        for source in (1, 2):
            inputs = ex_inputs(
                rs1_value=0x10020, rs2_value=0x55, imm=-16, alu_src_b=ALU_B_IMM,
                mem_valid=int(producer == "MEM"), mem_rd=source,
                mem_result=0x10040 if source == 1 else 0xAA,
                wb_valid=int(producer == "WB"), wb_rd=source,
                wb_data=0x10040 if source == 1 else 0xAA,
            )
            await check_execute_stage(
                dut, name=f"Address/store source x{source} from {producer}", inputs=inputs,
                expected_result=0x10030 if source == 1 else 0x10010,
                expected_store=0x55 if source == 1 else 0xAA,
                expected_fire=0, expected_target=0x10030 if source == 1 else 0x10010,
            )
    # Reverse the two producers feeding a taken branch.
    await check_execute_stage(
        dut, name="Branch rs1 from WB, rs2 from MEM",
        inputs=ex_inputs(imm=32, alu_src_a=ALU_A_PC, alu_src_b=ALU_B_IMM,
                         control_flow=CF_BRANCH, branch_kind=BR_LT_SIGNED,
                         mem_valid=1, mem_rd=2, mem_result=1,
                         wb_valid=1, wb_rd=1, wb_data=0xFFFF_FFFF),
        expected_result=0x1020, expected_store=1, expected_fire=1, expected_target=0x1020,
    )


@cocotb.test()
async def test_redirect_gates(dut):
    gate_cases = ((1, 1), (0, 1), (1, 0), (0, 0))
    cases = (
        #flow, branch operand B, expected fire for each (valid, allowed)
        (CF_NONE, 7, (0, 0, 0, 0)),
        (CF_BRANCH, 8, (0, 0, 0, 0)),
        (CF_BRANCH, 7, (1, 0, 0, 0)),
        (CF_JAL, 8, (1, 0, 0, 0)),
        (CF_JALR, 8, (1, 0, 0, 0)),
    )
    for flow, b, fires in cases:
        for (valid, allowed), fire in zip(gate_cases, fires, strict=True):
            jalr = flow == CF_JALR
            jump = flow in (CF_JAL, CF_JALR)
            await check_execute_stage(
                dut, name=f"Redirect gates flow={flow}, valid={valid}, allowed={allowed}",
                inputs=ex_inputs(pc=0x1000, imm=1 if jalr else 32,
                                 rs1_value=7, rs2_value=b,
                                 alu_src_a=ALU_A_RS1 if jalr else ALU_A_PC,
                                 alu_src_b=ALU_B_IMM, control_flow=flow,
                                 result_src=RESULT_PC_PLUS_4 if jump else RESULT_ALU,
                                 instruction_valid=valid, advance_allowed=allowed),
                expected_result=0x1004 if jump else 0x1020, expected_store=b,
                expected_fire=fire, expected_target=8 if jalr else 0x1020,
            )


@cocotb.test()
async def test_consecutive_control_changes(dut):
    cases = (
        #flow, source A, link selector, rs1, rs2, expected result, expected target, fire
        (CF_JALR, ALU_A_RS1, RESULT_PC_PLUS_4, 0x3001, 7, 0x1004, 0x3004, 1),
        (CF_JAL, ALU_A_PC, RESULT_PC_PLUS_4, 5, 7, 0x1004, 0x1004, 1),
        (CF_NONE, ALU_A_RS1, RESULT_ALU, 5, 7, 9, 9, 0),
        (CF_BRANCH, ALU_A_PC, RESULT_ALU, 7, 7, 0x1004, 0x1004, 1),
        (CF_BRANCH, ALU_A_PC, RESULT_ALU, 7, 8, 0x1004, 0x1004, 0),
    )
    for flow, source, result_src, a, b, result, target, fire in cases:
        await check_execute_stage(
            dut, name="Consecutive control change",
            inputs=ex_inputs(imm=4, rs1_value=a, rs2_value=b, alu_src_a=source,
                             alu_src_b=ALU_B_IMM, result_src=result_src, control_flow=flow),
            expected_result=result, expected_store=b, expected_fire=fire, expected_target=target,
        )
    for mem_valid, wb_valid, result in ((1, 1, 13), (0, 1, 23), (0, 0, 5)):
        await check_execute_stage(
            dut, name="Consecutive producer change",
            inputs=ex_inputs(rs1_value=2, rs2_value=3, mem_valid=mem_valid,
                             mem_result=10, wb_valid=wb_valid, wb_rd=1, wb_data=20),
            expected_result=result, expected_store=3, expected_fire=0, expected_target=result,
        )


@cocotb.test()
async def test_fence_and_control_diagnostics(dut):
    # Defined leaf fallbacks remain observable through an invalid EX entry.
    for op in (10, 11, 12, 13, 14, 15):
        await check_execute_stage(
            dut, name=f"Invalid entry, ALU reserved code {op}",
            inputs=ex_inputs(instruction_valid=0, alu_op=op, rs1_value=2, rs2_value=3),
            expected_result=0xDEAD_BEEF, expected_store=3,
            expected_fire=0, expected_target=0xDEAD_BEEF,
        )
    await check_execute_stage(
        dut, name="Invalid entry, reserved operand A selector",
        inputs=ex_inputs(instruction_valid=0, alu_src_a=3, rs2_value=1),
        expected_result=0xDEAD_BEF0, expected_store=1,
        expected_fire=0, expected_target=0xDEAD_BEF0,
    )
    # FENCE consumes no ALU result; unused binary selector payload is not a design error.
    await check_execute_stage(
        dut, name="FENCE with unused reserved payload",
        inputs=ex_inputs(alu_op=15, alu_src_a=3, branch_kind=2),
        expected_result=None, expected_store=None, expected_fire=0, expected_target=None,
        uses_alu=False, uses_operand_a=False,
    )
    await check_execute_stage(
        dut, name="Invalid entry with arbitrary binary controls",
        inputs=ex_inputs(instruction_valid=0, alu_op=15, alu_src_a=3,
                         branch_kind=2, control_flow=CF_BRANCH),
        expected_result=None, expected_store=None, expected_fire=0, expected_target=None,
    )
    await check_execute_stage(
        dut, name="Nonbranch ignores unused branch selector",
        inputs=ex_inputs(rs1_value=2, rs2_value=3, branch_kind=2),
        expected_result=5, expected_store=3, expected_fire=0, expected_target=5,
    )
    # Validate the checker itself without accepting illegal live stimulus as a passing DUT test.
    for bad in (
        ex_inputs(alu_op=10), ex_inputs(alu_src_a=3),
        ex_inputs(control_flow=CF_BRANCH, branch_kind=2),
        ex_inputs(control_flow=CF_BRANCH, branch_kind=3),
        ex_inputs(alu_op=15, advance_allowed=0),
    ):
        try:
            check_control(bad)
        except AssertionError:
            pass
        else:
            raise AssertionError(f"Control checker accepted illegal live inputs: {bad}")
