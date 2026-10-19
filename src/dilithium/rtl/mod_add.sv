// mod_add.sv

import dilithium_pkg::*;

module mod_add (
    input  poly_coeff_t a,
    input  poly_coeff_t b,
    output poly_coeff_t sum
);
    logic [Q_BITS:0] s;   // one extra bit to catch overflow past Q

    assign s   = a + b;
    assign sum = (s >= Q) ? (s - Q) : s[Q_BITS-1:0];

endmodule
