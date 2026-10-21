//------------------------------------------------------------------------------
// Module      : request_formatter
// Description : Combinational address, byte-enable and store-data formatting.
// Author      : Viet Nguyen To Quoc
// Date        : 2026-10-21
//------------------------------------------------------------------------------

module request_formatter
    import riscv_pkg::*;
(
    input logic [ADDR_WIDTH-1:0] effective_address,
    input logic [DATA_WIDTH-1:0] store_data,
    input mem_type_t mem_type,

    output logic [ADDR_WIDTH-1:0] aligned_address,
    output logic [DATA_WIDTH-1:0] write_data,
    output logic [3:0] byte_enable
);
    assign aligned_address = {effective_address[ADDR_WIDTH-1:2], 2'b00};

    always_comb begin : request_formatter
        //default
        write_data = 32'hDEAD_BEEF;
        byte_enable = 4'b0000;

        case (mem_type)
            MEM_BYTE, MEM_BYTE_U: begin
                byte_enable = 4'b0001 << effective_address[1:0];
                write_data  = {(DATA_WIDTH/8){store_data[7:0]}};
            end

            MEM_HALF, MEM_HALF_U: begin
                byte_enable = 4'b0011 << effective_address[1:0]; //only offsets 0/2 are supported; misaligned-access handling later
                write_data  = {(DATA_WIDTH/16){store_data[15:0]}};
            end

            MEM_WORD: begin
                byte_enable = 4'b1111;
                write_data  = store_data;
            end

            default: begin
                byte_enable = 4'b0000;
                write_data  = '0;
            end
        endcase
    end
endmodule
