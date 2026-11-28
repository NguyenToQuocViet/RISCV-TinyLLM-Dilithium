// Author: Nguyen Hung
// License: Apache-2.0
package keccak_pkg;
    localparam int KECCAK_STATE       = 1600;
    localparam int KECCAK256_CAPACITY = 1088;
    localparam int KECCAK512_CAPACITY = 576;
    localparam int SHAKE128_CAPACITY  = 1344;
    localparam int SHAKE256_CAPACITY  = 1088;
    localparam int W                  = 64;
    localparam int LOG2_W             = 6;
    localparam int LOG2ROUNDNR_FINAL256 = 6;
    localparam int KECCAK256_WORDS    = KECCAK256_CAPACITY / W;
    localparam int KECCAK512_WORDS    = KECCAK512_CAPACITY / W;
    localparam int ROUNDNR256         = 24;
    localparam int ROUNDNR_FINAL      = 1;
    localparam int CTR_SHORT          = 16;
    localparam int CTR_FULL           = 64;
    localparam int CTR_SIZE           = CTR_FULL;

    typedef logic [W-1:0] plane_t [0:4];
    typedef plane_t state_t [0:4];
    typedef logic [KECCAK_STATE/5-1:0] state_table_t [0:4];

    function automatic int get_keccak_capacity(input int hs);
        if (hs == 256)
            return KECCAK256_CAPACITY;
        if (hs == 512)
            return KECCAK512_CAPACITY;
        return SHAKE128_CAPACITY;
    endfunction

    function automatic state_table_t str2table(input logic [KECCAK_STATE-1:0] str);
        state_table_t result;
        for (int i = 0; i < 5; i++)
            result[i] = str[KECCAK_STATE*(5-i)/5-1 -: KECCAK_STATE/5];
        return result;
    endfunction

    function automatic int divceil(input int a, input int b);
        return (a + b - 1) / b;
    endfunction
endpackage
