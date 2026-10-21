//------------------------------------------------------------------------------
// Module      : load_formatter
// Description : Combinational load-lane selection and sign/zero extension.
// Author      : Viet Nguyen To Quoc
// Date        : 2026-10-21
//------------------------------------------------------------------------------

module load_formatter
    import riscv_pkg::*;
(
    input logic [DATA_WIDTH-1:0] read_data,
    input logic [ADDR_WIDTH-1:0] effective_address,
    input mem_type_t mem_type,

    output logic [DATA_WIDTH-1:0] load_result
);
    logic [1:0] byte_offset;
    assign byte_offset = effective_address[1:0];

    always_comb begin : load_formatter
        //default
        load_result = 32'hDEAD_BEEF;

        case (mem_type)
            MEM_BYTE: begin
                if (byte_offset == 2'b00) begin
                    load_result = {{24{read_data[7]}}, read_data[7:0]};
                end

                if (byte_offset == 2'b01) begin
                    load_result = {{24{read_data[15]}}, read_data[15:8]};
                end

                if (byte_offset == 2'b10) begin
                    load_result = {{24{read_data[23]}}, read_data[23:16]};
                end

                if (byte_offset == 2'b11) begin
                    load_result = {{24{read_data[31]}}, read_data[31:24]};
                end
            end

            MEM_HALF: begin
                if (byte_offset == 2'b00) begin
                    load_result = {{16{read_data[15]}}, read_data[15:0]};
                end

                if (byte_offset == 2'b10) begin
                    load_result = {{16{read_data[31]}}, read_data[31:16]};
                end
            end

            MEM_WORD: begin
                load_result = read_data;
            end

            MEM_BYTE_U: begin
                if (byte_offset == 2'b00) begin
                    load_result = {24'h0, read_data[7:0]};
                end

                if (byte_offset == 2'b01) begin
                    load_result = {24'h0, read_data[15:8]};
                end

                if (byte_offset == 2'b10) begin
                    load_result = {24'h0, read_data[23:16]};
                end

                if (byte_offset == 2'b11) begin
                    load_result = {24'h0, read_data[31:24]};
                end
            end

            MEM_HALF_U: begin
                if (byte_offset == 2'b00) begin
                    load_result = {16'h0, read_data[15:0]};
                end

                if (byte_offset == 2'b10) begin
                    load_result = {16'h0, read_data[31:16]};
                end
            end

            default: begin
                load_result = 32'hDEAD_BEEF;
            end
        endcase
    end
endmodule
