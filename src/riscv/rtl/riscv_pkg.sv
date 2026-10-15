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
endpackage : riscv_pkg
