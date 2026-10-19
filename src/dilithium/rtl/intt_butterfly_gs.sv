// intt_butterfly_gs.sv
// Inverse NTT butterfly (Gentleman-Sande, decimation-in-frequency), one
// layer of FIPS 204 Algorithm 42 (NTT^-1):
//     a' = a + b              (mod Q)
//     b' = zeta * (a - b)     (mod Q)

import dilithium_pkg::*;

module intt_butterfly_gs (
    input  logic         clk,
    input  logic         rst_n,
    input  logic         valid_in,
    input  poly_coeff_t  a_in,
    input  poly_coeff_t  b_in,
    input  logic [31:0]  zeta_mont,
    output logic         valid_out,
    output poly_coeff_t  a_out,
    output poly_coeff_t  b_out
);

    poly_coeff_t sum_ab, diff_ab;

    mod_add u_add (.a(a_in), .b(b_in), .sum (sum_ab));   // a + b
    mod_sub u_sub (.a(a_in), .b(b_in), .diff(diff_ab));  // a - b

    // register sum_ab for 2 cycles to line up with the multiplier latency
    poly_coeff_t sum_d1, sum_d2;
    logic        valid_d1;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            sum_d1   <= '0;
            sum_d2   <= '0;
            valid_d1 <= 1'b0;
        end else begin
            sum_d1   <= sum_ab;
            sum_d2   <= sum_d1;
            valid_d1 <= valid_in;
        end
    end

    assign a_out = sum_d2;

    mont_mul u_mul (
        .clk       (clk),
        .rst_n     (rst_n),
        .valid_in  (valid_in),
        .a         ({{(32-Q_BITS){1'b0}}, diff_ab}),
        .b         (zeta_mont),
        .valid_out (valid_out),
        .result    (b_out)
    );

endmodule
