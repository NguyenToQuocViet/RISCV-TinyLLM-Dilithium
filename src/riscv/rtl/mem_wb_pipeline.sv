//------------------------------------------------------------------------------
// Module      : mem_wb_pipeline
// Description : MEM/WB pipeline register for the results and writeback control.
// Author      : Viet Nguyen To Quoc
// Date        : 2026-11-06
//------------------------------------------------------------------------------

module mem_wb_pipeline
    import riscv_pkg::*;
(
    //system interface
    input logic clk,
    input logic rst_n,

    //hcu interface
    input logic stall,
    input logic flush,

    //mem interface
    input logic valid_i,
    input logic [DATA_WIDTH-1:0] ex_result_i,
    input logic [DATA_WIDTH-1:0] load_result_i,

    input logic wb_src_i,

    input logic [4:0] rd_i,
    input logic reg_write_i,

    //wb interface
    output logic valid_o,
    output logic [DATA_WIDTH-1:0] ex_result_o,
    output logic [DATA_WIDTH-1:0] load_result_o,

    output logic wb_src_o,

    output logic [4:0] rd_o,
    output logic reg_write_o
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
            ex_result_o   <= ex_result_i;
            load_result_o <= load_result_i;
            wb_src_o      <= wb_src_i;
            rd_o          <= rd_i;
            reg_write_o   <= reg_write_i;
        end
    end
endmodule
