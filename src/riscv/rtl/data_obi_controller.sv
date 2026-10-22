module data_obi_controller
    import riscv_pkg::*;
(
    //system interface
    input logic clk,
    input logic rst_n,

    //MEM interface
    input logic instruction_valid,
    input logic mem_en,
    input logic mem_write,
    input logic [ADDR_WIDTH-1:0] aligned_address,
    input logic [3:0] byte_enable,
    input logic [DATA_WIDTH-1:0] write_data,

    output logic [DATA_WIDTH-1:0] read_data,
    output logic mem_wait,

    //OBI interface
    output logic req,
    output logic [ADDR_WIDTH-1:0] addr,
    output logic we,
    output logic [3:0] be,
    output logic [DATA_WIDTH-1:0] wdata,
    output logic rready,

    input logic [DATA_WIDTH-1:0] rdata,
    input logic gnt,
    input logic rvalid
);
    logic outstanding;
    logic memory_owner;

    //payload routing
    assign addr      = aligned_address;
    assign we        = mem_write;
    assign be        = byte_enable;
    assign wdata     = write_data;
    assign read_data = rdata;
    assign rready    = 1'b1;

    assign memory_owner = instruction_valid && mem_en;

    //request and pipeline wait
    always_comb begin : transaction_control
        req      = 1'b0;
        mem_wait = 1'b0;

        if (memory_owner) begin
            if (!outstanding) begin
                //present request and wait for acceptance
                req      = 1'b1;
                mem_wait = 1'b1;
            end else begin
                //request accepted; wait for response
                req      = 1'b0;
                mem_wait = !rvalid;
            end
        end
    end

    //transaction ownership
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            outstanding <= 1'b0;
        end else if (outstanding) begin
            if (rvalid) begin
                outstanding <= 1'b0;
            end
        end else begin
            if (req && gnt) begin
                outstanding <= 1'b1;
            end
        end
    end

endmodule
