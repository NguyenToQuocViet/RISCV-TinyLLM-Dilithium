// Author: Nguyen Hung
// License: Nguyen Hung
module coeff_decomposer (
    input  logic        rst,
    input  logic        clk,
    input  logic        valid_i,
    output logic        ready_i,
    input  logic [2:0]  sec_lvl,
    input  logic [23:0] di,
    output logic [23:0] doa = '0,
    output logic [23:0] dob = '0,
    output logic        valid_o,
    input  logic        ready_o
);
    localparam logic [22:0] Q = 23'd8380417;

    logic [4:0] valid_sr = '0;
    logic [23:0] di_buffer;
    logic signed [55:0] a1_0;
    logic signed [55:0] a1_1;
    logic signed [55:0] a1_2;
    logic signed [55:0] a0_0;
    logic signed [55:0] a0_1;
    logic signed [55:0] a0_2;
    logic [23:0] sub_val;
    logic [5:0] map1_out;

    assign ready_i = ready_o;
    assign sub_val = ((((Q - 1) / 2 - a0_1) >> 31) & Q);
    assign valid_o = valid_sr[4];

    decomp_map1 map1 (
        .sec_lvl(sec_lvl),
        .din(di_buffer[22:0]),
        .dout(map1_out)
    );

    always_ff @(posedge clk) begin
        if (ready_o) begin
            valid_sr <= rst ? '0 : {valid_sr[3:0], valid_i};
            di_buffer <= di;
            a1_0 <= map1_out;
            a1_1 <= a1_0;
            a1_2 <= a1_1;
            dob <= a1_2;

            a0_0 <= di_buffer;
            a0_2 <= a0_1 - sub_val;
            doa <= (a0_2 < 0) ? a0_2 + Q : a0_2;

            if (sec_lvl == 3'd2)
                a0_1 <= a0_0 - ((a1_0 << 17) + (a1_0 << 16) -
                                 (a1_0 << 12) - (a1_0 << 11));
            else
                a0_1 <= a0_0 - ((a1_0 << 19) - (a1_0 << 9));
        end
    end
endmodule
