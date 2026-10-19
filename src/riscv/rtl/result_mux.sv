//------------------------------------------------------------------------------
// Module      : result_mux
// Description : Combinational selection of the ALU result or jump-link value.
// Author      : Viet Nguyen To Quoc
// Date        : 2026-10-19
//------------------------------------------------------------------------------

module result_mux
    import riscv_pkg::*;
(
    input logic [DATA_WIDTH-1:0] alu_result,
    input logic [ADDR_WIDTH-1:0] pc_plus_4,
    input result_src_t result_src,
    output logic [DATA_WIDTH-1:0] result
);
    always_comb begin : result_mux
        result = alu_result;    //default

        case (result_src)
            RESULT_ALU: result = alu_result;
            RESULT_PC_PLUS_4: result = pc_plus_4;
        endcase
    end
endmodule
