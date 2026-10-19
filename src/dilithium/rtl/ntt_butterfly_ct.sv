// ntt_butterfly_ct.sv
// Forward NTT butterfly (Cooley-Tukey, decimation-in-time), one layer
// of FIPS 204 Algorithm 41 (NTT):
//     a' = a + zeta * b   (mod Q)
//     b' = a - zeta * b   (mod Q)

import dilithium_pkg::*;

module ntt_butterfly_ct (
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

    // t = zeta * b_in (mod Q), Montgomery multiply, 2-cycle latency
    logic         mul_valid;
    poly_coeff_t  t;

    mont_mul u_mul (
        .clk       (clk),
        .rst_n     (rst_n),
        .valid_in  (valid_in),
        .a         ({{(32-Q_BITS){1'b0}}, b_in}),
        .b         (zeta_mont),
        .valid_out (mul_valid),
        .result    (t)
    );

    // delay a_in by 2 cycles to line up with t
    poly_coeff_t a_d1, a_d2;
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            a_d1 <= '0;
            a_d2 <= '0;
        end else begin
            a_d1 <= a_in;
            a_d2 <= a_d1;
        end
    end

    mod_add u_add (.a(a_d2), .b(t), .sum (a_out));
    mod_sub u_sub (.a(a_d2), .b(t), .diff(b_out));

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) valid_out <= 1'b0;
        else        valid_out <= mul_valid;
    end

endmodule
