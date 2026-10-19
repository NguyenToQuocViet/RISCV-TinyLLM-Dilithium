// dilithium_pkg.sv

package dilithium_pkg;

    // Field modulus 
    localparam int unsigned Q       = 32'd8_380_417;   // 0x007FE001
    localparam int unsigned Q_BITS  = 23;               // ceil(log2(Q))
    localparam int unsigned N       = 256;               // ring degree (coeffs/poly)

    // Verified numerically: Q^-1 mod 2^32 = 58728449,
    //                        -Q^-1 mod 2^32 = 4236238847 (0xFC7FDFFF).
    localparam int unsigned QINV_REDC = 32'hFC7FDFFF;

    // Selector (ML-DSA-44/65/87)
    typedef enum logic [1:0] {
        SEC_44 = 2'd0,
        SEC_65 = 2'd1,
        SEC_87 = 2'd2
    } sec_level_e;

    // Signed 23-bit ring element, representation in [0, Q-1].
    typedef logic [Q_BITS-1:0] poly_coeff_t;

endpackage
