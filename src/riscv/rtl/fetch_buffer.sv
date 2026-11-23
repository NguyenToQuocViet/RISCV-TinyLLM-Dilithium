//------------------------------------------------------------------------------
// Module      : fetch_buffer
// Description : Indexed pc and instruction payload array; no reset and no control.
// Author      : Viet Nguyen To Quoc
// Date        : 2026-11-06
//------------------------------------------------------------------------------

module fetch_buffer
    import riscv_pkg::*;
(
    input logic clk,

    input logic pc_write,
    input logic [1:0] pc_write_slot,
    input logic [ADDR_WIDTH-1:0] pc_write_data,

    input logic instruction_write,
    input logic [1:0] instruction_write_slot,
    input logic [INSTR_WIDTH-1:0] instruction_write_data,

    input logic [1:0] present_slot,
    input logic present_direct,
    input logic [1:0] fetch_slot,
    input logic fetch_bypass,

    output logic [ADDR_WIDTH-1:0] present_pc,
    output logic [ADDR_WIDTH-1:0] fetch_pc,
    output logic [INSTR_WIDTH-1:0] fetch_instruction
);
    logic [ADDR_WIDTH-1:0]  pc [FETCH_DEPTH];
    logic [INSTR_WIDTH-1:0] instruction [FETCH_DEPTH];

    assign present_pc           = present_direct ? pc_write_data : pc[present_slot];
    assign fetch_pc             = pc[fetch_slot];
    assign fetch_instruction    = fetch_bypass ? instruction_write_data : instruction[fetch_slot];

    //pc payload (no reset)
    always_ff @(posedge clk) begin
        if (pc_write) begin
            pc[pc_write_slot] <= pc_write_data;
        end
    end

    //instruction payload (no reset)
    always_ff @(posedge clk) begin
        if (instruction_write) begin
            instruction[instruction_write_slot] <= instruction_write_data;
        end
    end
endmodule
