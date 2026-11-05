//------------------------------------------------------------------------------
// Module      : prefetch_unit
// Description : Connects fetch_controller_unit, fetch_buffer and fetch_obi_interface.
// Author      : Viet Nguyen To Quoc
// Date        : 2026-11-05
//------------------------------------------------------------------------------

module prefetch_unit
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
    logic alloc_fire;
    logic kill;
    logic alloc_valid;
    logic [ADDR_WIDTH-1:0] alloc_pc;

    fetch_controller_unit if_fetch_controller_unit (
        .clk        (clk),
        .rst_n      (rst_n),

        .redirect_fire  (redirect_fire),
        .redirect_target(redirect_target),

        .alloc_fire     (alloc_fire),

        .kill           (kill),
        .alloc_valid    (alloc_valid),
        .alloc_pc       (alloc_pc)
    );

    logic present_valid;
    logic [ADDR_WIDTH-1:0] present_pc;
    logic request_fire;
    logic raw_response_transfer;
    logic [INSTR_WIDTH-1:0] response_data;

    fetch_buffer if_fetch_buffer (
        .clk            (clk),
        .rst_n          (rst_n),

        .kill           (kill),
        .alloc_valid    (alloc_valid),
        .alloc_pc       (alloc_pc),

        .fetch_accept   (fetch_accept),

        .request_fire   (request_fire),
        .raw_response_transfer(raw_response_transfer),
        .response_data  (response_data),

        .alloc_fire     (alloc_fire),

        .present_valid  (present_valid),
        .present_pc     (present_pc),

        .fetch_valid    (fetch_valid),
        .fetch_pc       (fetch_pc),
        .fetch_instruction(fetch_instruction)
    );

    fetch_obi_interface if_fetch_obi_interface (
        .rst_n          (rst_n),

        .present_valid  (present_valid),
        .present_pc     (present_pc),

        .request_fire   (request_fire),
        .raw_response_transfer(raw_response_transfer),
        .response_data  (response_data),

        .req            (req),
        .addr           (addr),
        .we             (we),
        .be             (be),
        .wdata          (wdata),
        .rready         (rready),

        .rdata          (rdata),
        .gnt            (gnt),
        .rvalid         (rvalid)
    );
endmodule
