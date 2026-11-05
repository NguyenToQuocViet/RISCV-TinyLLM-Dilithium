//------------------------------------------------------------------------------
// Module      : fetch_stage
// Description : IF stage boundary; connects its ports to prefetch_unit by name.
// Author      : Viet Nguyen To Quoc
// Date        : 2026-11-05
//------------------------------------------------------------------------------

module fetch_stage
    import riscv_pkg::*;
(
    input logic clk,
    input logic rst_n,

    input logic fetch_accept,

    input logic redirect_fire,
    input logic [ADDR_WIDTH-1:0] redirect_target,

    input logic gnt,
    input logic rvalid,
    input logic [INSTR_WIDTH-1:0] rdata,

    output logic req,
    output logic [ADDR_WIDTH-1:0] addr,
    output logic rready,
    output logic we,
    output logic [3:0] be,
    output logic [DATA_WIDTH-1:0] wdata,

    output logic fetch_valid,
    output logic [ADDR_WIDTH-1:0] fetch_pc,
    output logic [INSTR_WIDTH-1:0] fetch_instruction
);
    prefetch_unit if_prefetch_unit (
        .clk               (clk),
        .rst_n             (rst_n),

        .fetch_accept      (fetch_accept),

        .redirect_fire     (redirect_fire),
        .redirect_target   (redirect_target),

        .gnt               (gnt),
        .rvalid            (rvalid),
        .rdata             (rdata),

        .req               (req),
        .addr              (addr),
        .rready            (rready),
        .we                (we),
        .be                (be),
        .wdata             (wdata),

        .fetch_valid       (fetch_valid),
        .fetch_pc          (fetch_pc),
        .fetch_instruction (fetch_instruction)
    );
endmodule
