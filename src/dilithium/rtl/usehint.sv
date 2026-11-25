// Author: Luke Beckwith
// License: Apache-2.0
`timescale 1ns/1ps

module usehint #(
    parameter int OUTPUT_W = 4,
    parameter int COEFF_W  = 24,
    parameter int W        = 64
) (
    input  logic                         rst,
    input  logic                         clk,
    input  logic                         start,
    input  logic [2:0]                   sec_lvl,
    input  logic [W-1:0]                 di,
    input  logic                         valid_i,
    output logic                         ready_i,
    input  logic [OUTPUT_W*COEFF_W-1:0]  poly0_i,
    input  logic [OUTPUT_W*COEFF_W-1:0]  poly1_i,
    input  logic                         poly_valid_i,
    output logic                         poly_ready_i,
    output logic [OUTPUT_W*COEFF_W-1:0]  poly_o,
    output logic                         poly_valid_o,
    input  logic                         poly_ready_o
);
    typedef enum logic [1:0] { INIT, RECEIVE_HINT, EXPAND_HINT, APPLY_HINT } state_t;
    state_t state;
    logic [7:0] hint_cnt [0:7];
    logic [671:0] hint_addr;
    logic [2047:0] hint_poly;
    logic [10:0] ctr, ctr_next, hint_offset;
    logic [9:0] pos, pos_next, hint_len;
    logic [6:0] hint_addr_len;
    logic [3:0] k_count, num_hints;
    logic [7:0] next_hint;
    logic [5:0] final_shift;

    always_comb begin
        case (sec_lvl)
            3'd2: begin k_count = 4; hint_len = 671; hint_addr_len = 80; end
            3'd3: begin k_count = 6; hint_len = 487; hint_addr_len = 55; end
            default: begin k_count = 8; hint_len = 663; hint_addr_len = 75; end
        endcase
        num_hints = k_count;
        for (int i = 0; i < 8; i++)
            hint_cnt[i] = i < k_count ? hint_addr[8*(k_count-i-1) +: 8] : '0;
        next_hint = hint_addr[hint_len - pos*8 -: 8];

        hint_offset = '0;
        for (int i = 0; i < 8; i++) begin
            if (i < k_count && ctr >= hint_cnt[i])
                hint_offset = 256*(i+1);
        end

        ready_i = 1'b0;
        poly_ready_i = poly_ready_o;
        poly_o = poly1_i;
        poly_valid_o = 1'b0;
        ctr_next = ctr;
        pos_next = pos;
        final_shift = 8*((ctr+1)*8 - hint_addr_len - num_hints);

        if (sec_lvl != 3'd2) begin
            for (int i = 0; i < OUTPUT_W; i++) begin
                if (hint_poly[ctr+i])
                    poly_o[24*i +: 24] = (poly0_i[24*i +: 24] > (8380417-1)/32 || poly0_i[24*i +: 24] == 0) ?
                                            (poly1_i[24*i +: 24] == 0 ? 15 : poly1_i[24*i +: 24] - 1) :
                                            (poly1_i[24*i +: 24] == 15 ? 0 : poly1_i[24*i +: 24] + 1);
            end
        end else begin
            for (int i = 0; i < OUTPUT_W; i++) begin
                if (hint_poly[ctr+i])
                    poly_o[24*i +: 24] = (poly0_i[24*i +: 24] > (8380417-1)/88 || poly0_i[24*i +: 24] == 0) ?
                                            (poly1_i[24*i +: 24] == 0 ? 43 : poly1_i[24*i +: 24] - 1) :
                                            (poly1_i[24*i +: 24] == 43 ? 0 : poly1_i[24*i +: 24] + 1);
            end
        end

        case (state)
            INIT: begin ctr_next = '0; pos_next = '0; end
            RECEIVE_HINT: begin
                ctr_next = valid_i ? (((ctr+1)*8 > hint_addr_len+num_hints) ? '0 : ctr+1) : ctr;
                ready_i = valid_i;
                pos_next = '0;
            end
            EXPAND_HINT: begin
                ctr_next = (ctr+1 >= hint_cnt[k_count-1]) ? '0 : ctr+1;
                pos_next = pos+1;
            end
            APPLY_HINT: begin
                poly_valid_o = poly_valid_i;
                ctr_next = (poly_valid_o && poly_ready_o) ? ctr+OUTPUT_W : ctr;
            end
            default: begin end
        endcase
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            state <= INIT;
            ctr <= '0;
            pos <= '0;
            hint_addr <= '0;
            hint_poly <= '0;
        end else begin
            ctr <= ctr_next;
            pos <= pos_next;
            case (state)
                INIT: if (start) begin
                    hint_addr <= '0;
                    hint_poly <= '0;
                    state <= RECEIVE_HINT;
                end
                RECEIVE_HINT: begin
                    if ((ctr+1)*8 > hint_addr_len+num_hints)
                        hint_addr <= (hint_addr << (64-final_shift)) | (di >> final_shift);
                    else if (valid_i)
                        hint_addr <= {hint_addr[607:0], di};
                    if (valid_i && (ctr+1)*8 > hint_addr_len+num_hints)
                        state <= EXPAND_HINT;
                end
                EXPAND_HINT: begin
                    hint_poly[next_hint+hint_offset] <= 1'b1;
                    if (ctr+1 >= hint_cnt[k_count-1]) state <= APPLY_HINT;
                end
                APPLY_HINT: if (ctr == k_count*256) state <= INIT;
                default: state <= INIT;
            endcase
        end
    end
endmodule
