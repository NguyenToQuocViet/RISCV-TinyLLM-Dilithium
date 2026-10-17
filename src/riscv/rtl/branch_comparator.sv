//------------------------------------------------------------------------------
// Module      : branch_comparator
// Description : Combinational 32-bit comparison for six branch conditions.
// Author      : Viet Nguyen To Quoc
// Date        : 2026-10-16
//------------------------------------------------------------------------------

module branch_comparator
    import riscv_pkg::*;
(
    input logic [DATA_WIDTH-1:0] operand_a,
    input logic [DATA_WIDTH-1:0] operand_b,
    input branch_kind_t branch_kind,

    output logic branch_condition
);
    always_comb begin : branch_comparator
        branch_condition = 1'b0;

        case (branch_kind)
            BR_EQ:          branch_condition = (operand_a == operand_b) ? 1'b1 : 1'b0;
            BR_NE:          branch_condition = (operand_a != operand_b) ? 1'b1 : 1'b0;
            BR_LT_SIGNED:   branch_condition = ($signed(operand_a) < $signed(operand_b)) ? 1'b1 : 1'b0;
            BR_GE_SIGNED:   branch_condition = ($signed(operand_a) >= $signed(operand_b)) ? 1'b1 : 1'b0;
            BR_LT_UNSIGNED: branch_condition = (operand_a < operand_b) ? 1'b1 : 1'b0;
            BR_GE_UNSIGNED: branch_condition = (operand_a >= operand_b) ? 1'b1 : 1'b0;

            default: branch_condition = 1'b0;
        endcase
    end
endmodule
