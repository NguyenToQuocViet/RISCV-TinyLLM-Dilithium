// Author: Nguyen Hung
// License: Nguyen Hung
module zero_strip #(
    parameter int OUTPUT_W = 4,
    parameter int COEFF_W = 23,
    parameter int MAX_LVL = 20,
    parameter int W = 64
) (
    input  logic [4:0]                    encode_lvl,
    input  logic [OUTPUT_W*COEFF_W-1:0]   di,
    output logic [MAX_LVL*OUTPUT_W-1:0]   dout
);
    localparam int OUT_W = MAX_LVL * OUTPUT_W;
    logic [OUT_W-1:0] lane0;
    logic [OUT_W-1:0] lane1;
    logic [OUT_W-1:0] lane2;
    logic [OUT_W-1:0] lane3;

    always_comb begin
        lane0 = '0;
        lane1 = '0;
        lane2 = '0;
        lane3 = '0;
        lane0[COEFF_W-1:0] = di[COEFF_W*0 +: COEFF_W];
        lane1[COEFF_W-1:0] = di[COEFF_W*1 +: COEFF_W];
        lane2[COEFF_W-1:0] = di[COEFF_W*2 +: COEFF_W];
        lane3[COEFF_W-1:0] = di[COEFF_W*3 +: COEFF_W];
        dout = lane0 | (lane1 << encode_lvl) | (lane2 << (2*encode_lvl)) |
               (lane3 << (3*encode_lvl));
    end
endmodule
