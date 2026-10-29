//------------------------------------------------------------------------------
// Module      : register_file
// Description : Store x1-x31 with two bypassed read ports and one write port.
// Author      : Viet Nguyen To Quoc
// Date        : 2026-10-29
//------------------------------------------------------------------------------

module register_file
    import riscv_pkg::*;
(
    //system
    input logic clk,

    input logic [4:0] rs1_id,
    input logic [4:0] rs2_id,

    input logic rf_write_fire,
    input logic [4:0] wb_rd,
    input logic [DATA_WIDTH-1:0] wb_data,

    output logic [DATA_WIDTH-1:0] rs1_value,
    output logic [DATA_WIDTH-1:0] rs2_value
);
    //31 32-bit registers
    logic [DATA_WIDTH-1:0] rf_data [1:31];  //verible

    //combinational read
    //read-after-write forwarding
    always_comb begin : read_register
        //default
        rs1_value = rf_data[rs1_id];
        rs2_value = rf_data[rs2_id];

        //2 read ports parralel
        if (rs1_id == 5'd0) begin
            rs1_value = 'd0;
        end else if (rf_write_fire && (wb_rd == rs1_id)) begin
            rs1_value = wb_data;
        end else begin
            rs1_value = rf_data[rs1_id];
        end

        if (rs2_id == 5'd0) begin
            rs2_value = 'd0;
        end else if (rf_write_fire && (wb_rd == rs2_id)) begin
            rs2_value = wb_data;
        end else begin
            rs2_value = rf_data[rs2_id];
        end
    end

    //sync write
    //no reset
    always_ff @(posedge clk) begin : write_register
        if (rf_write_fire && (wb_rd != 5'd0)) begin
            rf_data[wb_rd] <= wb_data;
        end
    end
endmodule
