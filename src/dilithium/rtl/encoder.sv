// Author: Nguyen Hung
// License: Nguyen Hung
module encoder #(
    parameter int OUTPUT_W = 4,
    parameter int COEFF_W = 23,
    parameter int MAX_LVL = 20,
    parameter int W = 64
) (
    input  logic                        rst,
    input  logic                        clk,
    input  logic [2:0]                  sec_lvl,
    input  logic [2:0]                  encode_mode,
    input  logic                        valid_i,
    output logic                        ready_i,
    input  logic [OUTPUT_W*COEFF_W-1:0] di,
    output logic [W-1:0]                dout,
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
    localparam logic [2:0] NONE = 3'd0;
    localparam logic [2:0] ETA = 3'd1;
    localparam logic [2:0] T0 = 3'd2;
    localparam logic [2:0] T1 = 3'd3;
    localparam logic [2:0] GAMMA1 = 3'd4;

    logic [4:0] encode_lvl;
    logic [2:0] mode;
    logic [OUTPUT_W*COEFF_W-1:0] di_uncentered;
    logic [OUTPUT_W*COEFF_W-1:0] di_uncentered_buffer;
    logic [MAX_LVL*OUTPUT_W-1:0] stripped;
    logic [OUTPUT_W*COEFF_W-1:0] di_buffer;
    logic [1:0] valid_buffer;
    logic [255:0] piso;
    logic [9:0] piso_len;
    logic [9:0] piso_len_next;
    logic [9:0] buffer_len [0:1];

    generate
        for (genvar i = 0; i < OUTPUT_W; i++) begin : gen_uncenter
            uncenter_coeff uncenter (
                .sec_lvl(sec_lvl),
                .mode(mode),
                .di(di_buffer[COEFF_W*i +: 23]),
                .dout(di_uncentered[COEFF_W*i +: 23])
            );
        end
    endgenerate

    zero_strip #(
        .OUTPUT_W(OUTPUT_W),
        .COEFF_W(COEFF_W),
        .MAX_LVL(MAX_LVL),
        .W(W)
    ) z_strip (
        .encode_lvl(encode_lvl),
        .di(di_uncentered_buffer),
        .dout(stripped)
    );

    always_comb begin
        encode_lvl = '0;
        mode = NONE;
        casez ({sec_lvl, encode_mode})
            {3'b???, ENCODE_T0}: begin
                encode_lvl = 5'd13;
                mode = T0;
            end
            {3'b???, ENCODE_T1}: begin
                encode_lvl = 5'd10;
                mode = T1;
            end
            {3'd2, ENCODE_S2},
            {3'd5, ENCODE_S2},
            {3'd2, ENCODE_S1},
            {3'd5, ENCODE_S1}: begin
                encode_lvl = 5'd3;
                mode = ETA;
            end
            {3'd3, ENCODE_S2},
            {3'd3, ENCODE_S1}: begin
                encode_lvl = 5'd4;
                mode = ETA;
            end
            {3'd3, ENCODE_W1},
            {3'd5, ENCODE_W1}: begin
                encode_lvl = 5'd4;
            end
            {3'd2, ENCODE_W1}: begin
                encode_lvl = 5'd6;
            end
            {3'd2, ENCODE_Z}: begin
                encode_lvl = 5'd18;
                mode = GAMMA1;
            end
            {3'd3, ENCODE_Z},
            {3'd5, ENCODE_Z}: begin
                encode_lvl = 5'd20;
                mode = GAMMA1;
            end
            default: begin end
        endcase

        valid_o = (piso_len >= W);
        piso_len_next = (valid_o && ready_o) ? piso_len - W : piso_len;
        ready_i = 1'b1;
        dout = piso[W-1:0];
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            di_uncentered_buffer <= '0;
            di_buffer <= '0;
            valid_buffer <= '0;
            buffer_len[0] <= '0;
            buffer_len[1] <= '0;
            piso_len <= '0;
            piso <= '0;
        end else begin
            di_uncentered_buffer <= di_uncentered;
            di_buffer <= di;
            valid_buffer[0] <= ready_i && valid_i;
            valid_buffer[1] <= valid_buffer[0];
            buffer_len[0] <= (ready_i && valid_i) ? OUTPUT_W*encode_lvl : '0;
            buffer_len[1] <= buffer_len[0];
            piso_len <= piso_len_next + buffer_len[1];

            if (valid_buffer[1]) begin
                if (valid_o && ready_o)
                    piso <= (piso >> W) | ({192'd0, stripped} << piso_len_next);
                else
                    piso <= piso | ({192'd0, stripped} << piso_len_next);
            end else if (valid_o && ready_o) begin
                piso <= piso >> W;
            end
        end
    end
endmodule
