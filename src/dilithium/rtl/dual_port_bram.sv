// dual_port_bram.sv
// Simple dual-port RAM (1 write port, 1 read port, independent
// addresses), synchronous read. Target: FPGA block RAM inference.
// Used for the polynomial working memory (Poly Memory / IOBUF banks).

module dual_port_bram #(
    parameter int unsigned DATA_WIDTH = 23,
    parameter int unsigned DEPTH      = 256,
    localparam int unsigned ADDR_WIDTH = $clog2(DEPTH)
)(
    input  logic                     clk,

    input  logic                     wr_en,
    input  logic [ADDR_WIDTH-1:0]    wr_addr,
    input  logic [DATA_WIDTH-1:0]    wr_data,

    input  logic [ADDR_WIDTH-1:0]    rd_addr,
    output logic [DATA_WIDTH-1:0]    rd_data
);

    (* ram_style = "block" *)
    logic [DATA_WIDTH-1:0] mem [0:DEPTH-1];

    always_ff @(posedge clk) begin
        if (wr_en) mem[wr_addr] <= wr_data;
        rd_data <= mem[rd_addr];   // 1-cycle read latency
    end

endmodule
