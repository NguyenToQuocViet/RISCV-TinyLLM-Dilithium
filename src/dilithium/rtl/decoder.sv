// Author: Nguyen Hung
// License: Nguyen Hung
module decoder #(
    parameter int OUTPUT_W = 4,
    parameter int COEFF_W = 23,
    parameter int W = 64
) (
    input  logic                        rst,
    input  logic                        clk,
    input  logic [2:0]                  sec_lvl,
    input  logic [2:0]                  encode_modei,
    input  logic                        valid_i,
    output logic                        ready_i,
    input  logic [W-1:0]                di,
    output logic [OUTPUT_W*COEFF_W-1:0] samples,
    output logic                        valid_o,
    input  logic                        ready_o
);
    localparam logic [22:0] DILITHIUM_Q = 23'd8380417;
    localparam logic [2:0] ENCODE_T0 = 3'd0;
    localparam logic [2:0] ENCODE_T1 = 3'd1;
    localparam logic [2:0] ENCODE_S1 = 3'd2;
    localparam logic [2:0] ENCODE_S2 = 3'd3;
    localparam logic [2:0] ENCODE_W1 = 3'd4;
    localparam logic [2:0] ENCODE_Z = 3'd5;
    localparam logic [22:0] GAMMA1_2 = 23'd131072;
    localparam logic [22:0] GAMMA1_35 = 23'd524288;

    logic [2:0] encode_mode;
    logic [3*W-1:0] sipo_in;
    logic [3*W-1:0] sipo_in_shift;
    logic [199:0] sipo_out;
    logic [OUTPUT_W*COEFF_W-1:0] sipo_out_in;
    logic [OUTPUT_W*COEFF_W-1:0] sipo_out_in_shift;
    logic [8:0] sipo_in_len;
    logic [8:0] sipo_in_len_next;
    logic [7:0] sipo_out_len;
    logic [7:0] sipo_out_len_next;
    logic [3:0] eta;
    logic [2*W-1:0] di_shift;
    logic [5:0] encode_lvl;

    always_comb begin
        eta = '0;
        encode_lvl = '0;
        sipo_out_in = '0;

        casez ({sec_lvl, encode_mode})
            {3'b???, ENCODE_T0}: begin
                encode_lvl = 6'd13;
                for (int i = 0; i < OUTPUT_W; i++)
                    sipo_out_in[COEFF_W*i +: COEFF_W] =
                        (sipo_in[13*i +: 13] > 13'd4096) ?
                        DILITHIUM_Q - sipo_in[13*i +: 13] + 13'd4096 :
                        13'd4096 - sipo_in[13*i +: 13];
            end
            {3'b???, ENCODE_T1}: begin
                encode_lvl = 6'd10;
                for (int i = 0; i < OUTPUT_W; i++)
                    sipo_out_in[COEFF_W*i +: COEFF_W] = {sipo_in[10*i +: 10], 13'd0};
            end
            {3'd2, ENCODE_S2},
            {3'd5, ENCODE_S2},
            {3'd2, ENCODE_S1},
            {3'd5, ENCODE_S1}: begin
                encode_lvl = 6'd3;
                eta = 4'd2;
                for (int i = 0; i < OUTPUT_W; i++)
                    sipo_out_in[COEFF_W*i +: COEFF_W] =
                        (sipo_in[3*i +: 3] > eta) ? DILITHIUM_Q - sipo_in[3*i +: 3] + eta :
                                                     eta - sipo_in[3*i +: 3];
            end
            {3'd3, ENCODE_S2},
            {3'd3, ENCODE_S1}: begin
                encode_lvl = 6'd4;
                eta = 4'd4;
                for (int i = 0; i < OUTPUT_W; i++)
                    sipo_out_in[COEFF_W*i +: COEFF_W] =
                        (sipo_in[4*i +: 4] > eta) ? DILITHIUM_Q - sipo_in[4*i +: 4] + eta :
                                                     eta - sipo_in[4*i +: 4];
            end
            {3'd3, ENCODE_W1},
            {3'd5, ENCODE_W1}: begin
                encode_lvl = 6'd4;
                for (int i = 0; i < OUTPUT_W; i++)
                    sipo_out_in[COEFF_W*i +: COEFF_W] = sipo_in[4*i +: 4];
            end
            {3'd2, ENCODE_W1}: begin
                encode_lvl = 6'd6;
                for (int i = 0; i < OUTPUT_W; i++)
                    sipo_out_in[COEFF_W*i +: COEFF_W] = sipo_in[6*i +: 6];
            end
            {3'd2, ENCODE_Z}: begin
                encode_lvl = 6'd18;
                for (int i = 0; i < OUTPUT_W; i++) begin
                    if (sipo_in_len >= (i + 1) * 18)
                        sipo_out_in[COEFF_W*i +: COEFF_W] =
                            (sipo_in[18*i +: 18] > GAMMA1_2) ?
                            GAMMA1_2 + (DILITHIUM_Q - sipo_in[18*i +: 18]) :
                            GAMMA1_2 - sipo_in[18*i +: 18];
                end
            end
            {3'd3, ENCODE_Z},
            {3'd5, ENCODE_Z}: begin
                encode_lvl = 6'd20;
                for (int i = 0; i < OUTPUT_W; i++) begin
                    if (sipo_in_len >= (i + 1) * 20)
                        sipo_out_in[COEFF_W*i +: COEFF_W] =
                            (sipo_in[20*i +: 20] > GAMMA1_35) ?
                            GAMMA1_35 + DILITHIUM_Q - sipo_in[20*i +: 20] :
                            GAMMA1_35 - sipo_in[20*i +: 20];
                end
            end
            default: begin end
        endcase

        valid_o = (sipo_out_len >= OUTPUT_W*COEFF_W);
        ready_i = (sipo_in_len < 4*encode_lvl || (valid_o && 4*encode_lvl > 63));
        sipo_in_len_next = (ready_i && valid_i) ? sipo_in_len + W : sipo_in_len;
        sipo_out_len_next = (valid_o && ready_o) ? sipo_out_len - OUTPUT_W*COEFF_W : sipo_out_len;
        samples = sipo_out[OUTPUT_W*COEFF_W-1:0];
        sipo_in_shift = sipo_in >> (4*encode_lvl);

        if (valid_o && ready_o)
            sipo_out_in_shift = sipo_out_in << (sipo_out_len - OUTPUT_W*COEFF_W);
        else
            sipo_out_in_shift = sipo_out_in << sipo_out_len;

        if (sipo_in_len >= 4*encode_lvl)
            di_shift = ({{W{1'b0}}, di} << (sipo_in_len - 4*encode_lvl));
        else
            di_shift = ({{W{1'b0}}, di} << sipo_in_len);
    end

    always_ff @(posedge clk) begin
        encode_mode <= encode_modei;
        if (rst) begin
            sipo_in <= '0;
            sipo_out <= '0;
            sipo_in_len <= '0;
            sipo_out_len <= '0;
        end else begin
            if (sipo_out_len_next <= OUTPUT_W*COEFF_W) begin
                if (sipo_in_len >= 4*encode_lvl) begin
                    sipo_in_len <= sipo_in_len_next - 4*encode_lvl;
                    sipo_out_len <= sipo_out_len_next + OUTPUT_W*COEFF_W;
                    if (valid_i)
                        sipo_in <= sipo_in_shift | di_shift;
                    else
                        sipo_in <= sipo_in_shift;
                end else begin
                    sipo_in_len <= sipo_in_len_next;
                    sipo_out_len <= sipo_out_len_next;
                    if (valid_i)
                        sipo_in <= sipo_in | di_shift;
                end
            end else begin
                sipo_in_len <= sipo_in_len_next;
                sipo_out_len <= sipo_out_len_next;
            end

            if (valid_o && ready_o) begin
                if (sipo_in_len >= encode_lvl)
                    sipo_out <= (sipo_out >> (OUTPUT_W*COEFF_W)) | sipo_out_in_shift;
                else
                    sipo_out <= sipo_out >> (OUTPUT_W*COEFF_W);
            end else if (sipo_in_len >= encode_lvl) begin
                sipo_out <= sipo_out | sipo_out_in_shift;
            end
        end
    end
endmodule
