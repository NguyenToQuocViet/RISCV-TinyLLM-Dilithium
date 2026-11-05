//------------------------------------------------------------------------------
// Module      : fetch_controller_unit
// Description : Owns next_fetch_pc and drives allocation and kill to fetch_buffer.
// Author      : Viet Nguyen To Quoc
// Date        : 2026-11-05
//------------------------------------------------------------------------------

module fetch_controller_unit
    import riscv_pkg::*;
(
    input logic clk,
    input logic rst_n,

    input logic redirect_fire,
    input logic [ADDR_WIDTH-1:0] redirect_target,

    input logic alloc_fire,

    output logic kill,
    output logic alloc_valid,
    output logic [ADDR_WIDTH-1:0] alloc_pc
);
    logic [ADDR_WIDTH-1:0] next_fetch_pc;

    always_ff @(posedge clk or negedge rst_n) begin : fcu
        if (!rst_n) begin
            next_fetch_pc <= PC_RESET_VEC;
        end else if (redirect_fire) begin
            next_fetch_pc <= redirect_target;
        end else if (alloc_fire) begin
            next_fetch_pc <= next_fetch_pc + 32'd4;
        end else begin
            next_fetch_pc <= next_fetch_pc; //hold
        end
    end

    assign kill = redirect_fire;
    assign alloc_valid = 1'b1;      //always fetch
    assign alloc_pc = next_fetch_pc;
endmodule
