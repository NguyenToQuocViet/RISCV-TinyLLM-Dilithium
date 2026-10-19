//------------------------------------------------------------------------------
// Module      : operand_mux
// Description : Combinational selection of the two ALU operands.
// Author      : Viet Nguyen To Quoc
// Date        : 2026-10-19
//------------------------------------------------------------------------------

module operand_mux
    import riscv_pkg::*;
(
    input logic [DATA_WIDTH-1:0] rs1_value,
    input logic [DATA_WIDTH-1:0] rs2_value,

    input logic [DATA_WIDTH-1:0] pc,
    input logic [DATA_WIDTH-1:0] imm,

    input alu_src_a_t alu_src_a,
    input alu_src_b_t alu_src_b,

    output logic [DATA_WIDTH-1:0] operand_a,
    output logic [DATA_WIDTH-1:0] operand_b
);
    always_comb begin : operand_mux
        //default
        operand_a = rs1_value;
        operand_b = rs2_value;

        case (alu_src_a)
            ALU_A_RS1: operand_a = rs1_value;
            ALU_A_PC: operand_a = pc;
            ALU_A_ZERO: operand_a = 32'h0;

            default: operand_a = 32'hDEAD_BEEF;
        endcase

        case (alu_src_b)
            ALU_B_RS2: operand_b = rs2_value;
            ALU_B_IMM: operand_b = imm;
        endcase
    end

endmodule
