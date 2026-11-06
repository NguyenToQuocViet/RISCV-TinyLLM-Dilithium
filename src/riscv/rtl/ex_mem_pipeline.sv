//------------------------------------------------------------------------------
// Module      : ex_mem_pipeline
// Description : EX/MEM pipeline register for the EX result and memory control.
// Author      : Viet Nguyen To Quoc
// Date        : 2026-11-06
//------------------------------------------------------------------------------

module ex_mem_pipeline
    import riscv_pkg::*;
(
    //system interface
    input logic clk,
    input logic rst_n,

    //hcu interface
    input logic stall,
    input logic flush,

    //ex interface
    input logic valid_i,
    input logic [DATA_WIDTH-1:0] ex_result_i,
    input logic [DATA_WIDTH-1:0] store_data_i,

    input logic [4:0] rd_i,
    input logic reg_write_i,

    input logic mem_en_i,
    input logic mem_write_i,
    input mem_type_t mem_type_i,

    input logic wb_src_i,

    //mem interface
    output logic valid_o,
    output logic [DATA_WIDTH-1:0] ex_result_o,
    output logic [DATA_WIDTH-1:0] store_data_o,

    output logic [4:0] rd_o,
    output logic reg_write_o,

    output logic mem_en_o,
    output logic mem_write_o,
    output mem_type_t mem_type_o,

    output logic wb_src_o
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
            ex_result_o  <= ex_result_i;
            store_data_o <= store_data_i;
            rd_o         <= rd_i;
            reg_write_o  <= reg_write_i;
            mem_en_o     <= mem_en_i;
            mem_write_o  <= mem_write_i;
            mem_type_o   <= mem_type_i;
            wb_src_o     <= wb_src_i;
        end
    end
endmodule
