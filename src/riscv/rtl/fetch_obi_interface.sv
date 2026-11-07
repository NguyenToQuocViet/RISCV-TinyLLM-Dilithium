//------------------------------------------------------------------------------
// Module      : fetch_obi_interface
// Description : Stateless instruction OBI port for the selected fetch entry,
//               with request and raw response events to the fetch controller.
// Author      : Viet Nguyen To Quoc
// Date        : 2026-11-02
//------------------------------------------------------------------------------

module fetch_obi_interface
    import riscv_pkg::*;
(
    //system interface
    input logic rst_n,

    //fetch buffer interface
    input logic present_valid,
    input logic [ADDR_WIDTH-1:0] present_pc,

    output logic request_fire,
    output logic raw_response_transfer,
    output logic [INSTR_WIDTH-1:0] response_data,

    //OBI interface
    output logic req,
    output logic [ADDR_WIDTH-1:0] addr,
    output logic we,
    output logic [3:0] be,
    output logic [DATA_WIDTH-1:0] wdata,
    output logic rready,

    input logic [INSTR_WIDTH-1:0] rdata,
    input logic gnt,
    input logic rvalid
);
    //payload routing (no write)
    assign req      = present_valid;
    assign addr     = present_pc;
    assign rready   = 1'b1;
    assign we       = 1'b0;
    assign be       = 4'b1111;
    assign wdata    = '0;

    assign request_fire             = rst_n && req && gnt;
    assign raw_response_transfer    = rst_n && rvalid && rready;
    assign response_data            = rdata;
endmodule
