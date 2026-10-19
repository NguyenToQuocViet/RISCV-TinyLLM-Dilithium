// mont_mul.sv

import dilithium_pkg::*;

module mont_mul (
    input  logic        clk,
    input  logic        rst_n,
    input  logic         valid_in,
    input  logic [31:0]  a,
    input  logic [31:0]  b,
    output logic         valid_out,
    output poly_coeff_t  result
);

    // ---------------- Stage 1: integer product -------------------------
    logic         valid_s1;
    logic [63:0]  prod_s1;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            valid_s1 <= 1'b0;
            prod_s1  <= '0;
        end else begin
            valid_s1 <= valid_in;
            prod_s1  <= a * b;
        end
    end

    // ---------------- Stage 2: REDC reduction ---------------------------
    logic [31:0] m;        // m = (prod mod 2^32) * QINV_REDC mod 2^32
    logic [63:0] t_full;   // (prod + m*Q) >> 32, before final subtract

    assign m       = prod_s1[31:0] * QINV_REDC;
    assign t_full  = (prod_s1 + m * Q) >> 32;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            valid_out <= 1'b0;
            result    <= '0;
        end else begin
            valid_out <= valid_s1;
            result    <= (t_full >= Q) ? (t_full - Q) : t_full[Q_BITS-1:0];
        end
    end

endmodule
