//------------------------------------------------------------------------------
// Module      : alu
// Description : Combinational 32-bit arithmetic, logic, shift and comparison.
// Author      : Viet Nguyen To Quoc
// Date        : 2026-10-15
//------------------------------------------------------------------------------

module alu
    import riscv_pkg::*;
(
    input logic [DATA_WIDTH-1:0]    operand_a,
    input logic [DATA_WIDTH-1:0]    operand_b,
    input alu_op_t                  alu_op,

    output logic [DATA_WIDTH-1:0]   alu_result
);
    always_comb begin : alu
        alu_result = 32'h0; //default value

        case (alu_op)
            //arithmetic
            ALU_ADD: alu_result = operand_a + operand_b;
            ALU_SUB: alu_result = operand_a - operand_b;

            //logic
            ALU_AND: alu_result = operand_a & operand_b;
            ALU_OR : alu_result = operand_a | operand_b;
            ALU_XOR: alu_result = operand_a ^ operand_b;

            //shift
            ALU_SLL: alu_result = operand_a << operand_b[4:0];
            ALU_SRL: alu_result = operand_a >> operand_b[4:0];
            ALU_SRA: alu_result = $signed(operand_a) >>> operand_b[4:0];

            //comparison
            ALU_SLT: alu_result = ($signed(operand_a) < $signed(operand_b)) ? 32'h1 : 32'h0;
            ALU_SLTU:alu_result = (operand_a < operand_b) ? 32'h1 : 32'h0;

            default: alu_result = 32'hDEAD_BEEF;    //decode error
        endcase
    end
endmodule
