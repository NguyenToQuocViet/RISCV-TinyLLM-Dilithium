// Author: Nguyen Hung
// License: Nguyen Hung
module uncenter_coeff (
    input  logic [2:0]  sec_lvl,
    input  logic [2:0]  mode,
    input  logic [22:0] di,
    output logic [22:0] dout
);
    localparam logic [22:0] Q = 23'd8380417;
    localparam logic [2:0] M_NONE = 3'd0;
    localparam logic [2:0] M_ETA = 3'd1;
    localparam logic [2:0] M_T0 = 3'd2;
    localparam logic [2:0] M_T1 = 3'd3;
    localparam logic [2:0] M_GAMMA1 = 3'd4;

    logic [3:0] eta;
    logic [12:0] t;
    logic [19:0] gamma1;
    logic signed [23:0] t0;
    logic signed [23:0] t1;

    always_comb begin
        eta = (sec_lvl == 3) ? 4 : 2;
        t = 13'd4096;
        gamma1 = (sec_lvl == 2) ? (20'd1 << 17) : (20'd1 << 19);
        t1 = ({1'b0, di} + t - 1) >> 13;
        t0 = $signed({1'b0, di}) - (t1 <<< 13);

        case (mode)
            M_NONE:   dout = di;
            M_ETA:    dout = (di > eta) ? eta + Q - di : eta - di;
            M_T0:     dout = t - t0;
            M_T1:     dout = t1;
            M_GAMMA1: dout = (di > gamma1) ? gamma1 + Q - di : gamma1 - di;
            default:  dout = '0;
        endcase
    end
endmodule
