//------------------------------------------------------------------------------
// Module      : forwarding_unit
// Description : Combinational register-source forwarding with MEM over WB priority.
// Author      : Viet Nguyen To Quoc
// Date        : 2026-10-19
//------------------------------------------------------------------------------

module forwarding_unit
    import riscv_pkg::*;
(
    input logic [4:0] rs1_id,
    input logic [4:0] rs2_id,
    input logic [DATA_WIDTH-1:0] rs1_value,
    input logic [DATA_WIDTH-1:0] rs2_value,

    input logic [4:0] mem_rd,
    input logic [DATA_WIDTH-1:0] mem_result,
    input logic mem_valid,
    input logic mem_reg_write,
    input logic mem_wb_src,

    input logic [4:0] wb_rd,
    input logic [DATA_WIDTH-1:0] wb_data,
    input logic wb_valid,
    input logic wb_reg_write,

    output logic [DATA_WIDTH-1:0] fwd_rs1,
    output logic [DATA_WIDTH-1:0] fwd_rs2
);
    logic mem_eligible;
    logic wb_eligible;
    logic mem_rs1_match, mem_rs2_match;
    logic wb_rs1_match, wb_rs2_match;

    assign mem_eligible = mem_valid && mem_reg_write && !mem_wb_src && (mem_rd != 5'h0);
    assign wb_eligible  = wb_valid && wb_reg_write && (wb_rd != 5'h0);

    assign mem_rs1_match = (mem_rd == rs1_id);
    assign mem_rs2_match = (mem_rd == rs2_id);

    assign wb_rs1_match = (wb_rd == rs1_id);
    assign wb_rs2_match = (wb_rd == rs2_id);

    always_comb begin : forwarding_unit
        if (mem_eligible && mem_rs1_match)
            fwd_rs1 = mem_result;
        else if (wb_eligible && wb_rs1_match)
            fwd_rs1 = wb_data;
        else
            fwd_rs1 = rs1_value;

        if (mem_eligible && mem_rs2_match)
            fwd_rs2 = mem_result;
        else if (wb_eligible && wb_rs2_match)
            fwd_rs2 = wb_data;
        else
            fwd_rs2 = rs2_value;
    end
endmodule
