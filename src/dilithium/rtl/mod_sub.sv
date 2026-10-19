// mod_sub.sv

import dilithium_pkg::*;

module mod_sub (
    input  poly_coeff_t a,
    input  poly_coeff_t b,
    output poly_coeff_t diff
);
    logic signed [Q_BITS:0] d;   // extra sign bit

    assign d    = {1'b0, a} - {1'b0, b};
    assign diff = d[Q_BITS] ? (d + Q) : d[Q_BITS-1:0]; // add Q if negative

endmodule
