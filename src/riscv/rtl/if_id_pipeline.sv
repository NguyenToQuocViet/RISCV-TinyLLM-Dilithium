//------------------------------------------------------------------------------
// Module      : if_id_pipeline
// Description : IF/ID pipeline register for the fetched instruction and its PC.
// Author      : Viet Nguyen To Quoc
// Date        : 2026-11-06
//------------------------------------------------------------------------------

module if_id_pipeline
    import riscv_pkg::*;
(
    //system interface
    input logic clk,
    input logic rst_n,

    //hcu interface
    input logic stall,
    input logic flush,

    //if interface
    input logic valid_i,
    input logic [ADDR_WIDTH-1:0] pc_i,
    input logic [INSTR_WIDTH-1:0] instruction_i,

    //id interface
    output logic valid_o,
    output logic [ADDR_WIDTH-1:0] pc_o,
    output logic [INSTR_WIDTH-1:0] instruction_o
);
    logic capture;

    assign capture = valid_i && !stall && !flush;

    always_ff @(posedge clk or negedge rst_n) begin : valid_reg
        if (!rst_n) begin
            valid_o <= 1'b0;
        end else if (flush) begin
            valid_o <= 1'b0;
        end else if (stall) begin
            valid_o <= valid_o; //hold
        end else begin
            valid_o <= valid_i;
        end
    end

    //payload has no reset, PR-D1
    always_ff @(posedge clk) begin : payload_reg
        if (capture) begin
            pc_o          <= pc_i;
            instruction_o <= instruction_i;
        end
    end
endmodule
