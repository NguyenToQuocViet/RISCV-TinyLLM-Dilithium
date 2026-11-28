// Author: Nguyen Hung
// License: Apache-2.0
`timescale 1ns/1ps

module makehint #(
    parameter int OUTPUT_W = 4,
    parameter int COEFF_W  = 24,
    parameter int W        = 64
) (
    input  logic                         rst,
    input  logic                         clk,
    input  logic [2:0]                   sec_lvl,
    output logic                         reject_hint,
    input  logic [OUTPUT_W*COEFF_W-1:0]  poly0_ie,
    input  logic [OUTPUT_W*COEFF_W-1:0]  poly1_ie,
    input  logic                         poly_valid_ie,
    output logic                         poly_ready_i,
    output logic [W-1:0]                 hint_o,
    output logic                         hint_valid_o,
    input  logic                         hint_ready_o
);
    localparam logic [22:0] Q = 23'd8380417;
    typedef enum logic { MAKE_HINT, UNLOAD_HINT } state_t;
    state_t state;
    logic [OUTPUT_W*COEFF_W-1:0] poly0_i, poly1_i;
    logic poly_valid_i, reject_latched;
    logic [17:0] gamma2;
    logic [6:0] omega;
    logic [3:0] k_count;
    logic [3:0] hint_needed;
    logic [7:0] hint_addr [0:79];
    logic [7:0] poly_hint_cnt [0:7];
    logic [7:0] num_hints, ctr;
    logic [2:0] poly_num;

    always_comb begin
        gamma2 = (sec_lvl == 3'd2) ? 18'd95232 : 18'd261888;
        case (sec_lvl)
            3'd2: begin k_count = 4; omega = 80; end
            3'd3: begin k_count = 6; omega = 55; end
            default: begin k_count = 8; omega = 75; end
        endcase
        for (int i = 0; i < OUTPUT_W; i++)
            hint_needed[i] = !((poly0_i[24*i +: 24] <= gamma2) || (poly0_i[24*i +: 24] > Q - gamma2)) ||
                             ((poly0_i[24*i +: 24] == Q - gamma2) && (poly1_i[24*i +: 24] != 0));

        reject_hint = reject_latched;
        poly_ready_i = !reject_latched && state == MAKE_HINT;
        hint_o = '0;
        hint_valid_o = !reject_latched && state == UNLOAD_HINT;
        if (!reject_latched && state == UNLOAD_HINT) begin
            case (sec_lvl)
                3'd2: begin
                    if (8*ctr < omega)
                        for (int i = 0; i < 8; i++) hint_o[8*i +: 8] = hint_addr[ctr*8+i];
                    else
                        for (int i = 0; i < 8; i++) hint_o[8*i +: 8] = poly_hint_cnt[i];
                end
                3'd3: begin
                    if (8*(ctr+1) < omega)
                        for (int i = 0; i < 8; i++) hint_o[8*i +: 8] = hint_addr[ctr*8+i];
                    else if (8*ctr < omega) begin
                        for (int i = 0; i < 7; i++) hint_o[8*i +: 8] = hint_addr[ctr*8+i];
                        hint_o[63:56] = poly_hint_cnt[0];
                    end else
                        for (int i = 0; i < 7; i++) hint_o[8*i +: 8] = poly_hint_cnt[i+1];
                end
                default: begin
                    if (8*(ctr+1) < omega)
                        for (int i = 0; i < 8; i++) hint_o[8*i +: 8] = hint_addr[ctr*8+i];
                    else if (8*ctr < omega) begin
                        for (int i = 0; i < 3; i++) hint_o[8*i +: 8] = hint_addr[ctr*8+i];
                        hint_o[63:24] = {poly_hint_cnt[4], poly_hint_cnt[3], poly_hint_cnt[2], poly_hint_cnt[1], poly_hint_cnt[0]};
                    end else
                        for (int i = 0; i < 3; i++) hint_o[8*i +: 8] = poly_hint_cnt[i+5];
                end
            endcase
        end
    end

    always_ff @(posedge clk) begin
        poly0_i <= poly0_ie;
        poly1_i <= poly1_ie;
        poly_valid_i <= !rst && poly_valid_ie;
        if (rst) begin
            state <= MAKE_HINT;
            poly_num <= '0;
            ctr <= '0;
            num_hints <= '0;
            reject_latched <= 1'b0;
            hint_addr <= '{default: '0};
            poly_hint_cnt <= '{default: '0};
        end else if (!reject_latched) begin
            if (num_hints > omega) reject_latched <= 1'b1;
            case (state)
                MAKE_HINT: if (poly_valid_i) begin
                    ctr <= ctr + OUTPUT_W;
                    if (ctr == 8'd252) begin
                        ctr <= '0;
                        poly_hint_cnt[poly_num] <= num_hints + hint_needed[0] + hint_needed[1] + hint_needed[2] + hint_needed[3];
                        if (poly_num == k_count - 1) begin
                            state <= UNLOAD_HINT;
                            poly_num <= '0;
                        end else begin
                            poly_num <= poly_num + 1'b1;
                        end
                    end
                    if (hint_needed[0]) hint_addr[num_hints] <= ctr;
                    if (hint_needed[1]) hint_addr[num_hints + hint_needed[0]] <= ctr + 1;
                    if (hint_needed[2]) hint_addr[num_hints + hint_needed[0] + hint_needed[1]] <= ctr + 2;
                    if (hint_needed[3]) hint_addr[num_hints + hint_needed[0] + hint_needed[1] + hint_needed[2]] <= ctr + 3;
                    num_hints <= num_hints + hint_needed[0] + hint_needed[1] + hint_needed[2] + hint_needed[3];
                end
                UNLOAD_HINT: if (hint_ready_o) ctr <= ctr + 1'b1;
            endcase
        end
    end
endmodule
