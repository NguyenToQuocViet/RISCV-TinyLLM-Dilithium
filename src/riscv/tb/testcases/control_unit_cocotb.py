#------------------------------------------------------------------------------
# Module      : control_unit_cocotb
# Description : Directed per-operation and rejecting-word checks for the CU leaf.
# Author      : Viet Nguyen To Quoc
# Date        : 2026-10-31
#------------------------------------------------------------------------------

import cocotb
from cocotb.triggers import Timer

# Enum codes are literals taken from the accepted leaf records (plan control_unit):
#   alu_op      4b: ADD 0x0, SUB 0x1, AND 0x2, OR 0x3, XOR 0x4, SLL 0x5, SRL 0x6,
#                   SRA 0x7, SLT 0x8, SLTU 0x9                          (alu.md section 3)
#   alu_src_a   2b: RS1 0b00, PC 0b01, ZERO 0b10                        (operand-mux.md section 3)
#   alu_src_b   1b: RS2 0, IMM 1                                        (operand-mux.md section 3)
#   result_src  1b: ALU 0, PC_PLUS_4 1                                  (result-mux.md section 3)
#   branch_kind 3b: EQ 000, NE 001, LT_SIGNED 100, GE_SIGNED 101,
#                   LT_UNSIGNED 110, GE_UNSIGNED 111                    (branch-comparator.md section 3)
#   mem_type    3b: BYTE 000, HALF 001, WORD 010, BYTE_U 100, HALF_U 101 (request-formatter.md section 2)
#   control_flow 2b: NONE 00, BRANCH 01, JAL 10, JALR 11                (redirect-unit.md section 2)


async def check_control(dut, word, **expected):
    # Combinational block (section 2): one drive, 1 ns settle, then compare only the
    # outputs named by the caller. Don't-care cells (section 5.3 "-", section 5.4)
    # are never passed, so they are never compared.
    dut.instruction.value = word
    await Timer(1, unit="ns")
    for name, value in expected.items():
        observed = int(getattr(dut, name).value)
        assert observed == value, (
            f"instruction=0x{word:08X}: {name}: "
            f"expected {value:#b}, got {observed:#b}"
        )


@cocotb.test()
async def test_upper_and_jump_ops(dut):
    # Section 5.3 rows LUI, AUIPC, JAL, JALR; words from the plan (LUI/AUIPC/JAL/JALR are section 7).
    await check_control(dut, 0x5555_52B7,           # lui x5, 0x55555
        rs1_used=0, rs2_used=0, reg_write=1, mem_en=0,
        control_flow=0b00,   # CF_NONE
        wb_src=0,
        alu_op=0x0,          # ALU_ADD
        alu_src_a=0b10,      # ALU_A_ZERO
        alu_src_b=1,         # ALU_B_IMM
        result_src=0,        # RESULT_ALU
    )
    await check_control(dut, 0x1234_5197,           # auipc x3, 0x12345
        rs1_used=0, rs2_used=0, reg_write=1, mem_en=0,
        control_flow=0b00,   # CF_NONE
        wb_src=0,
        alu_op=0x0,          # ALU_ADD
        alu_src_a=0b01,      # ALU_A_PC
        alu_src_b=1,         # ALU_B_IMM
        result_src=0,        # RESULT_ALU
    )
    await check_control(dut, 0x0100_00EF,           # jal x1, .+16
        rs1_used=0, rs2_used=0, reg_write=1, mem_en=0,
        control_flow=0b10,   # CF_JAL
        wb_src=0,
        alu_op=0x0,          # ALU_ADD
        alu_src_a=0b01,      # ALU_A_PC
        alu_src_b=1,         # ALU_B_IMM
        result_src=1,        # RESULT_PC_PLUS_4
    )
    await check_control(dut, 0x0081_00E7,           # jalr x1, 8(x2)
        rs1_used=1, rs2_used=0, reg_write=1, mem_en=0,
        control_flow=0b11,   # CF_JALR
        wb_src=0,
        alu_op=0x0,          # ALU_ADD
        alu_src_a=0b00,      # ALU_A_RS1
        alu_src_b=1,         # ALU_B_IMM
        result_src=1,        # RESULT_PC_PLUS_4
    )


@cocotb.test()
async def test_branch_ops(dut):
    # Section 5.3 rows BEQ..BGEU. Common cells are the same for all six branches;
    # only branch_kind differs. wb_src and result_src are don't care and not checked.
    for word, branch_kind in (
        (0x0020_8863, 0b000),   # beq  x1, x2, .+16  BR_EQ
        (0x0020_9863, 0b001),   # bne  x1, x2, .+16  BR_NE
        (0x0020_C863, 0b100),   # blt  x1, x2, .+16  BR_LT_SIGNED
        (0x0020_D863, 0b101),   # bge  x1, x2, .+16  BR_GE_SIGNED
        (0x0020_E863, 0b110),   # bltu x1, x2, .+16  BR_LT_UNSIGNED (section 7)
        (0x0020_F863, 0b111),   # bgeu x1, x2, .+16  BR_GE_UNSIGNED
    ):
        await check_control(dut, word,
            rs1_used=1, rs2_used=1, reg_write=0, mem_en=0,
            control_flow=0b01,   # CF_BRANCH
            alu_op=0x0,          # ALU_ADD
            alu_src_a=0b01,      # ALU_A_PC
            alu_src_b=1,         # ALU_B_IMM
            branch_kind=branch_kind,
        )


@cocotb.test()
async def test_load_ops(dut):
    # Section 5.3 rows LB..LHU. Common cells are the same for all five loads;
    # only mem_type differs. branch_kind is don't care and not checked.
    for word, mem_type in (
        (0x0001_0083, 0b000),   # lb  x1, 0(x2)  MEM_BYTE
        (0x0001_1083, 0b001),   # lh  x1, 0(x2)  MEM_HALF
        (0x0001_2083, 0b010),   # lw  x1, 0(x2)  MEM_WORD
        (0x0081_4283, 0b100),   # lbu x5, 8(x2)  MEM_BYTE_U (section 7)
        (0x0001_5083, 0b101),   # lhu x1, 0(x2)  MEM_HALF_U
    ):
        await check_control(dut, word,
            rs1_used=1, rs2_used=0, reg_write=1, mem_en=1,
            control_flow=0b00,   # CF_NONE
            wb_src=1,
            alu_op=0x0,          # ALU_ADD
            alu_src_a=0b00,      # ALU_A_RS1
            alu_src_b=1,         # ALU_B_IMM
            result_src=0,        # RESULT_ALU
            mem_write=0,
            mem_type=mem_type,
        )


@cocotb.test()
async def test_store_ops(dut):
    # Section 5.3 rows SB, SH, SW. Common cells are the same for all three stores;
    # only mem_type differs. branch_kind is don't care and not checked.
    for word, mem_type in (
        (0x0031_0023, 0b000),   # sb x3, 0(x2)   MEM_BYTE
        (0x0061_1623, 0b001),   # sh x6, 12(x2)  MEM_HALF (section 7)
        (0x0031_2023, 0b010),   # sw x3, 0(x2)   MEM_WORD
    ):
        await check_control(dut, word,
            rs1_used=1, rs2_used=1, reg_write=0, mem_en=1,
            control_flow=0b00,   # CF_NONE
            wb_src=0,
            alu_op=0x0,          # ALU_ADD
            alu_src_a=0b00,      # ALU_A_RS1
            alu_src_b=1,         # ALU_B_IMM
            result_src=0,        # RESULT_ALU
            mem_write=1,
            mem_type=mem_type,
        )


@cocotb.test()
async def test_op_imm_ops(dut):
    # Section 5.3 rows ADDI..SRAI. Common cells are the same for all nine;
    # only alu_op differs.
    for word, alu_op in (
        (0x0001_0093, 0x0),   # addi  x1, x2, 0  ALU_ADD
        (0x0001_2093, 0x8),   # slti  x1, x2, 0  ALU_SLT
        (0x0001_3093, 0x9),   # sltiu x1, x2, 0  ALU_SLTU
        (0x0001_4093, 0x4),   # xori  x1, x2, 0  ALU_XOR
        (0x0001_6093, 0x3),   # ori   x1, x2, 0  ALU_OR
        (0x0001_7093, 0x2),   # andi  x1, x2, 0  ALU_AND
        (0x0031_1093, 0x5),   # slli  x1, x2, 3  ALU_SLL
        (0x0031_5093, 0x6),   # srli  x1, x2, 3  ALU_SRL
        (0x4031_5093, 0x7),   # srai  x1, x2, 3  ALU_SRA (section 7)
    ):
        await check_control(dut, word,
            rs1_used=1, rs2_used=0, reg_write=1, mem_en=0,
            control_flow=0b00,   # CF_NONE
            wb_src=0,
            alu_op=alu_op,
            alu_src_a=0b00,      # ALU_A_RS1
            alu_src_b=1,         # ALU_B_IMM
            result_src=0,        # RESULT_ALU
        )


@cocotb.test()
async def test_op_ops(dut):
    # Section 5.3 rows ADD..AND. Common cells are the same for all ten;
    # only alu_op differs.
    for word, alu_op in (
        (0x0031_00B3, 0x0),   # add  x1, x2, x3  ALU_ADD
        (0x4052_01B3, 0x1),   # sub  x3, x4, x5  ALU_SUB (section 7)
        (0x0031_10B3, 0x5),   # sll  x1, x2, x3  ALU_SLL
        (0x0031_20B3, 0x8),   # slt  x1, x2, x3  ALU_SLT
        (0x0031_30B3, 0x9),   # sltu x1, x2, x3  ALU_SLTU
        (0x0031_40B3, 0x4),   # xor  x1, x2, x3  ALU_XOR
        (0x0031_50B3, 0x6),   # srl  x1, x2, x3  ALU_SRL
        (0x4031_50B3, 0x7),   # sra  x1, x2, x3  ALU_SRA
        (0x0031_60B3, 0x3),   # or   x1, x2, x3  ALU_OR
        (0x0031_70B3, 0x2),   # and  x1, x2, x3  ALU_AND
    ):
        await check_control(dut, word,
            rs1_used=1, rs2_used=1, reg_write=1, mem_en=0,
            control_flow=0b00,   # CF_NONE
            wb_src=0,
            alu_op=alu_op,
            alu_src_a=0b00,      # ALU_A_RS1
            alu_src_b=0,         # ALU_B_RS2
            result_src=0,        # RESULT_ALU
        )


@cocotb.test()
async def test_fence(dut):
    # Section 5.3 row FENCE, section 7 word, C4: alu_op=ALU_ADD binds. The other
    # cells (wb_src, alu_src_a/b, result_src, branch_kind, mem_write, mem_type)
    # are don't care and not checked.
    await check_control(dut, 0x0FF0_000F,           # fence
        rs1_used=0, rs2_used=0, reg_write=0, mem_en=0,
        control_flow=0b00,   # CF_NONE
        alu_op=0x0,          # ALU_ADD (C4)
    )


@cocotb.test()
async def test_rejecting_words(dut):
    # Section 5.2 guard, section 7 rejecting words (one or two per rule L1..L9).
    # Only the three guarded enables are checked; every other output is don't care.
    for rule, word in (
        ("L1", 0x5551_0092),   # ADDI with i[1:0]=10
        ("L2", 0x0000_0073),   # ECALL (SYSTEM)
        ("L2", 0x0852_21AF),   # AMOSWAP.W (other opcode)
        ("L3", 0x0081_10E7),   # JALR, funct3=001
        ("L4", 0x0020_A863),   # BRANCH, funct3=010
        ("L4", 0x0020_B863),   # BRANCH, funct3=011
        ("L5", 0x0081_3283),   # LD, funct3=011
        ("L5", 0x0081_6283),   # LWU, funct3=110
        ("L6", 0x0061_3623),   # SD, funct3=011
        ("L6", 0x0061_4623),   # STORE, funct3=100
        ("L7", 0x0201_1093),   # SLLI, funct3=001, i[31:25]=0000001
        ("L7", 0x0201_5093),   # SRLI, funct3=101, i[31:25]=0000001
        ("L8", 0x0252_01B3),   # MUL
        ("L8", 0x4052_11B3),   # OP, funct7=0100000, funct3=001
        # L9 row cannot fail at this leaf: FENCE enables equal the guard values
        # (5.2, 5.3); kept for section 7 / C2 completeness.
        ("L9", 0x0000_100F),   # FENCE.I
    ):
        dut._log.info("rejecting word: %s 0x%08X", rule, word)
        await check_control(dut, word,
            reg_write=0,
            mem_en=0,
            control_flow=0b00,   # CF_NONE
        )
