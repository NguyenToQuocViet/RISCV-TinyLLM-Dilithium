//------------------------------------------------------------------------------
// Module      : memory_stage
// Description : Compose data OBI transactions and load/store formatting.
// Author      : Viet Nguyen To Quoc
// Date        : 2026-10-22
//------------------------------------------------------------------------------

module memory_stage
    import riscv_pkg::*;
(
    input logic clk,
    input logic rst_n,

    input logic instruction_valid,
    input logic [DATA_WIDTH-1:0] ex_result,
    input logic [DATA_WIDTH-1:0] store_data,
    input logic mem_en,
    input logic mem_write,
    input mem_type_t mem_type,

    output logic [DATA_WIDTH-1:0] load_result,

    output logic mem_wait,

    input logic gnt,
    input logic rvalid,
    input logic [DATA_WIDTH-1:0] rdata,

    output logic req,
    output logic [ADDR_WIDTH-1:0] addr,
    output logic [DATA_WIDTH-1:0] wdata,
    output logic we,
    output logic [3:0] be,
    output logic rready
);
    logic [ADDR_WIDTH-1:0] aligned_address;
    logic [DATA_WIDTH-1:0] write_data;
    logic [3:0] byte_enable;

    request_formatter mem_req_formatter (
        .effective_address  (ex_result),
        .store_data         (store_data),
        .mem_type           (mem_type),

        .aligned_address    (aligned_address),
        .write_data         (write_data),
        .byte_enable        (byte_enable)
    );

    logic [DATA_WIDTH-1:0] read_data;

    data_obi_controller mem_obi_controller (
        .clk                (clk),
        .rst_n              (rst_n),

        .instruction_valid  (instruction_valid),
        .mem_en             (mem_en),
        .mem_write          (mem_write),
        .aligned_address    (aligned_address),
        .byte_enable        (byte_enable),
        .write_data         (write_data),

        .read_data          (read_data),    //load formatter
        .mem_wait           (mem_wait),

        .req                (req),
        .addr               (addr),
        .we                 (we),
        .be                 (be),
        .wdata              (wdata),
        .rready             (rready),

        .rdata              (rdata),
        .gnt                (gnt),
        .rvalid             (rvalid)
    );

    load_formatter mem_load_formatter (
        .read_data          (read_data),
        .effective_address  (ex_result),
        .mem_type           (mem_type),

        .load_result        (load_result)
    );

endmodule
