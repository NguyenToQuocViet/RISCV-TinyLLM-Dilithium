//------------------------------------------------------------------------------
// Package     : riscv_pkg
// Description : Shared types and constants for the RISC-V core.
// Author      : Viet Nguyen To Quoc
// Date        : 2026-10-15
//------------------------------------------------------------------------------

package riscv_pkg;
    localparam int DATA_WIDTH = 32;
    localparam int ADDR_WIDTH = 32;

    typedef enum logic [3:0] {
        ALU_ADD = 4'h0,
        ALU_SUB = 4'h1,
        ALU_AND = 4'h2,
        ALU_OR  = 4'h3,
        ALU_XOR = 4'h4,
        ALU_SLL = 4'h5,
        ALU_SRL = 4'h6,
        ALU_SRA = 4'h7,
        ALU_SLT = 4'h8,
        ALU_SLTU= 4'h9
    } alu_op_t;

    typedef enum logic [2:0] {
        BR_EQ           = 3'h0,
        BR_NE           = 3'h1,
        BR_LT_SIGNED    = 3'h4,
        BR_GE_SIGNED    = 3'h5,
        BR_LT_UNSIGNED  = 3'h6,
        BR_GE_UNSIGNED  = 3'h7
    } branch_kind_t;

    typedef enum logic {
        RESULT_ALU      = 1'h0,
        RESULT_PC_PLUS_4= 1'h1
    } result_src_t;

    typedef enum logic [1:0] {
        ALU_A_RS1   = 2'h0,
        ALU_A_PC    = 2'h1,
        ALU_A_ZERO  = 2'h2
    } alu_src_a_t;

    typedef enum logic {
        ALU_B_RS2   = 1'h0,
        ALU_B_IMM   = 1'h1
    } alu_src_b_t;

    typedef enum logic [1:0] {
        CF_NONE     = 2'h0,
        CF_BRANCH   = 2'h1,
        CF_JAL      = 2'h2,
        CF_JALR     = 2'h3
    } control_flow_t;
endpackage : riscv_pkg
