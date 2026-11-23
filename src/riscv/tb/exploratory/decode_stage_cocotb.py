#------------------------------------------------------------------------------
# Module      : decode_stage_cocotb
# Description : Integrated tests of decode_stage with its real leaves (I-ID-01..06).
# Author      : Claude Code (Anthropic)
# Date        : 2026-11-19
#------------------------------------------------------------------------------

from cocotb.triggers import FallingEdge, RisingEdge

from xp_helpers import xp_test, drive, settle, expect, start_clock

ALU_ADD, ALU_OR, ALU_SLTU = 0x0, 0x3, 0x9
A_RS1, A_PC, A_ZERO = 0b00, 0b01, 0b10
B_RS2, B_IMM = 0, 1
RES_ALU, RES_LINK = 0, 1
BR_GE_SIGNED = 0b101
MEM_BYTE, MEM_HALF_U = 0b000, 0b101
CF_NONE, CF_BRANCH, CF_JAL, CF_JALR = 0b00, 0b01, 0b10, 0b11

# class -> (word, rs1_id, rs2_id, rd, imm or None)
WORDS = {
    "lui":   (0x7FFF_F6B7, 31, 31, 13, 0x7FFF_F000),
    "auipc": (0x8000_1717, 0, 0, 14, 0x8000_1000),
    "jal":   (0xFF9F_F7EF, 31, 25, 15, 0xFFFF_FFF8),
    "jalr":  (0xFFC8_8867, 17, 28, 16, 0xFFFF_FFFC),
    "bge":   (0xFF39_56E3, 18, 19, 13, 0xFFFF_FFEC),
    "lhu":   (0x006A_DA03, 21, 6, 20, 0x0000_0006),
    "sb":    (0xFF6B_8EA3, 23, 22, 29, 0xFFFF_FFFD),
    "ori":   (0x800C_EC13, 25, 0, 24, 0xFFFF_F800),
    "sltu":  (0x01CD_BD33, 27, 28, 26, None),
    "fence": (0x0FF0_000F, 0, 31, 0, None),
}

LUI = dict(rs1_used=0, rs2_used=0, reg_write=1, mem_en=0, control_flow=CF_NONE, wb_src=0, alu_op=ALU_ADD,
           alu_src_a=A_ZERO, alu_src_b=B_IMM, result_src=RES_ALU)
CLASS_OUTPUTS = {
    "lui": LUI,
    "auipc": dict(LUI, alu_src_a=A_PC),
    "jal": dict(rs1_used=0, rs2_used=0, reg_write=1, mem_en=0, control_flow=CF_JAL, wb_src=0, alu_op=ALU_ADD,
                alu_src_a=A_PC, alu_src_b=B_IMM, result_src=RES_LINK),
    "jalr": dict(rs1_used=1, rs2_used=0, reg_write=1, mem_en=0, control_flow=CF_JALR, wb_src=0, alu_op=ALU_ADD,
                 alu_src_a=A_RS1, alu_src_b=B_IMM, result_src=RES_LINK),
    "bge": dict(rs1_used=1, rs2_used=1, reg_write=0, mem_en=0, control_flow=CF_BRANCH, alu_op=ALU_ADD,
                alu_src_a=A_PC, alu_src_b=B_IMM, branch_kind=BR_GE_SIGNED),
    "lhu": dict(rs1_used=1, rs2_used=0, reg_write=1, mem_en=1, mem_write=0, mem_type=MEM_HALF_U,
                control_flow=CF_NONE, wb_src=1, alu_op=ALU_ADD, alu_src_a=A_RS1, alu_src_b=B_IMM,
                result_src=RES_ALU),
    "sb": dict(rs1_used=1, rs2_used=1, reg_write=0, mem_en=1, mem_write=1, mem_type=MEM_BYTE,
               control_flow=CF_NONE, wb_src=0, alu_op=ALU_ADD, alu_src_a=A_RS1, alu_src_b=B_IMM,
               result_src=RES_ALU),
    "ori": dict(rs1_used=1, rs2_used=0, reg_write=1, mem_en=0, control_flow=CF_NONE, wb_src=0, alu_op=ALU_OR,
                alu_src_a=A_RS1, alu_src_b=B_IMM, result_src=RES_ALU),
    "sltu": dict(rs1_used=1, rs2_used=1, reg_write=1, mem_en=0, control_flow=CF_NONE, wb_src=0,
                 alu_op=ALU_SLTU, alu_src_a=A_RS1, alu_src_b=B_RS2, result_src=RES_ALU),
    "fence": dict(rs1_used=0, rs2_used=0, reg_write=0, mem_en=0, control_flow=CF_NONE, alu_op=ALU_ADD),
}


async def check_decode(dut, instruction, **expected):
    drive(dut, instruction=instruction, rf_write_fire=0)
    await settle()
    expect(dut, **expected)


async def write_cycle(dut, rd, data):
    await FallingEdge(dut.clk)
    drive(dut, rf_write_fire=1, wb_rd=rd, wb_data=data)
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    drive(dut, rf_write_fire=0)


async def check_reads(dut, rs1_value, rs2_value):
    await settle()
    expect(dut, rs1_value=rs1_value, rs2_value=rs2_value)


@xp_test()
async def test_raw_field_extraction(dut):
    # I-ID-01: rs1_id, rs2_id and rd cut from bits 19:15, 24:20, 11:7 of any word
    for p in range(6, 26):
        rd = 1 << (p - 7) if 7 <= p <= 11 else 0
        rs1 = 1 << (p - 15) if 15 <= p <= 19 else 0
        rs2 = 1 << (p - 20) if 20 <= p <= 24 else 0
        await check_decode(dut, 1 << p, rs1_id=rs1, rs2_id=rs2, rd=rd)
    await check_decode(dut, 0xFFFF_FFFF, rs1_id=31, rs2_id=31, rd=31)
    for word, rs1, rs2, rd, _ in WORDS.values():
        await check_decode(dut, word, rs1_id=rs1, rs2_id=rs2, rd=rd)


@xp_test()
async def test_decode_one_operation_per_class(dut):
    # I-ID-02: every leaf output reaches its stage port, one word per class
    for name, (word, rs1, rs2, rd, imm) in WORDS.items():
        extra = {} if imm is None else {"imm": imm}
        await check_decode(dut, word, rs1_id=rs1, rs2_id=rs2, rd=rd, **extra, **CLASS_OUTPUTS[name])


@xp_test()
async def test_unsupported_words_guard(dut):
    # I-ID-03: unsupported words force reg_write, mem_en, control_flow inactive; raw fields still follow
    for word, rs1, rs2, rd in ((0x0000_0000, 0, 0, 0), (0xFFFF_FFFF, 31, 31, 31), (0x0000_0073, 0, 0, 0),
                               (0x3003_12F3, 6, 0, 5), (0x0252_01B3, 4, 5, 3)):
        await check_decode(dut, word, reg_write=0, mem_en=0, control_flow=CF_NONE,
                           rs1_id=rs1, rs2_id=rs2, rd=rd)


@xp_test()
async def test_register_read_by_instruction_fields(dut):
    # I-ID-04: rs1_id and rs2_id select the read ports; rd does not follow wb_rd
    start_clock(dut)
    drive(dut, instruction=0, rf_write_fire=0, wb_rd=0, wb_data=0)
    await write_cycle(dut, 7, 0x1111_1111)
    await write_cycle(dut, 9, 0x2222_2222)
    drive(dut, wb_rd=12, instruction=0x0093_81B3)
    await check_reads(dut, 0x1111_1111, 0x2222_2222)
    expect(dut, rs1_id=7, rs2_id=9, rd=3)
    drive(dut, instruction=0x0074_81B3)
    await check_reads(dut, 0x2222_2222, 0x1111_1111)


@xp_test()
async def test_wb_bypass_trace(dut):
    # I-ID-05: WB-to-ID bypass on each port, none without rf_write_fire (section 7 trace)
    start_clock(dut)
    drive(dut, instruction=0, rf_write_fire=0, wb_rd=0, wb_data=0)
    await write_cycle(dut, 7, 0x1111_1111)
    await write_cycle(dut, 9, 0x2222_2222)
    drive(dut, instruction=0x0003_8193, rf_write_fire=0, wb_rd=7, wb_data=0xDDDD_DDDD)
    await settle()
    expect(dut, rs1_value=0x1111_1111)
    drive(dut, rf_write_fire=1)
    await settle()
    expect(dut, rs1_value=0xDDDD_DDDD)
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    drive(dut, rf_write_fire=0, wb_data=0xEEEE_EEEE)
    await settle()
    expect(dut, rs1_value=0xDDDD_DDDD)
    await FallingEdge(dut.clk)
    drive(dut, rf_write_fire=1, wb_rd=7, wb_data=0xAAAA_AAAA, instruction=0x0093_81B3)
    await check_reads(dut, 0xAAAA_AAAA, 0x2222_2222)
    drive(dut, instruction=0x0074_81B3)
    await check_reads(dut, 0x2222_2222, 0xAAAA_AAAA)
    drive(dut, instruction=0x0073_81B3)
    await check_reads(dut, 0xAAAA_AAAA, 0xAAAA_AAAA)


@xp_test()
async def test_x0_through_stage(dut):
    # I-ID-06: x0 reads zero on both ports, a write to it changes nothing
    start_clock(dut)
    drive(dut, instruction=0, rf_write_fire=0, wb_rd=0, wb_data=0)
    await write_cycle(dut, 7, 0x1111_1111)
    drive(dut, instruction=0x0000_01B3, rf_write_fire=1, wb_rd=0, wb_data=0xEEEE_EEEE)
    await check_reads(dut, 0x0000_0000, 0x0000_0000)
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    drive(dut, rf_write_fire=0)
    await check_reads(dut, 0x0000_0000, 0x0000_0000)
    drive(dut, instruction=0x0003_81B3)
    await check_reads(dut, 0x1111_1111, 0x0000_0000)
