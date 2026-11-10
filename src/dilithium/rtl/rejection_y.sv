// Author: Luke Beckwith
// License: Apache-2.0
`timescale 1ns/1ps

module rejection_y #(
    parameter int W        = 64,
    parameter int SAMPLE_W = 23,
    parameter int BUS_W    = 4
) (
    input  logic                       rst,
    input  logic                       clk,
    input  logic [2:0]                 sec_lvl,
    input  logic                       valid_i,
    output logic                       ready_i,
    input  logic [W-1:0]               rdi,
    output logic [SAMPLE_W*BUS_W-1:0]  samples,
    output logic                       valid_o,
    input  logic                       ready_o
);
    localparam logic [22:0] DILITHIUM_Q = 23'd8380417;
    localparam logic [19:0] GAMMA2_LIMIT = 20'd131072;
    localparam logic [19:0] GAMMA35_LIMIT = 20'd524288;
    localparam logic [7:0] OUTPUT_CAPACITY = 8'(SAMPLE_W * BUS_W);
    localparam logic [7:0] SAMPLE_BITS = 8'(SAMPLE_W);

    logic [4:0] rdi_sample_w;
    logic [19:0] gamma_limit;
    logic [79:0] sipo_in, sipo_in_shift;
    logic [137:0] sipo_out;
    logic [3*SAMPLE_W-1:0] sipo_out_in;
    logic [19:0] rej_lane0, rej_lane1, rej_lane2;
    logic [22:0] sample0, sample1, sample2;
    logic rej_lane0_valid, rej_lane1_valid, rej_lane2_valid;
    logic [1:0] num_valid;
    logic [6:0] sipo_in_len, sipo_in_len_next;
    logic [7:0] sipo_out_len, sipo_out_len_next;
    logic [10:0] shift_in_amt;

    always_comb begin
        rdi_sample_w = (sec_lvl == 3'd2) ? 5'd18 : 5'd20;
        gamma_limit = (sec_lvl == 3'd2) ? GAMMA2_LIMIT : GAMMA35_LIMIT;
        ready_i = sipo_in_len < 3 * rdi_sample_w;
        valid_o = sipo_out_len >= OUTPUT_CAPACITY;

        if (sec_lvl == 3'd2) begin
            rej_lane0 = {2'd0, sipo_in[17:0]};
            rej_lane1 = {2'd0, sipo_in[35:18]};
            rej_lane2 = {2'd0, sipo_in[53:36]};
        end else begin
            rej_lane0 = sipo_in[19:0];
            rej_lane1 = sipo_in[39:20];
            rej_lane2 = sipo_in[59:40];
        end

        if (sipo_in_len >= 3 * rdi_sample_w)
            shift_in_amt = 3 * rdi_sample_w;
        else if (sipo_in_len >= 2 * rdi_sample_w)
            shift_in_amt = 2 * rdi_sample_w;
        else if (sipo_in_len >= {2'd0, rdi_sample_w})
            shift_in_amt = {6'd0, rdi_sample_w};
        else
            shift_in_amt = '0;

        sample0 = (rej_lane0 > gamma_limit) ? {3'd0, gamma_limit} + DILITHIUM_Q - {3'd0, rej_lane0} : {3'd0, gamma_limit} - {3'd0, rej_lane0};
        sample1 = (rej_lane1 > gamma_limit) ? {3'd0, gamma_limit} + DILITHIUM_Q - {3'd0, rej_lane1} : {3'd0, gamma_limit} - {3'd0, rej_lane1};
        sample2 = (rej_lane2 > gamma_limit) ? {3'd0, gamma_limit} + DILITHIUM_Q - {3'd0, rej_lane2} : {3'd0, gamma_limit} - {3'd0, rej_lane2};
        rej_lane0_valid = sipo_in_len >= {2'd0, rdi_sample_w};
        rej_lane1_valid = sipo_in_len >= 2 * rdi_sample_w;
        rej_lane2_valid = sipo_in_len >= 3 * rdi_sample_w;
        num_valid = rej_lane0_valid + rej_lane1_valid + rej_lane2_valid;
        if (!rej_lane0_valid) sample0 = '0;
        if (!rej_lane1_valid) sample1 = '0;
        if (!rej_lane2_valid) sample2 = '0;

        sipo_in_shift = sipo_in >> shift_in_amt;
        sipo_in_len_next = (valid_i && ready_i) ? sipo_in_len + W[6:0] : sipo_in_len;
        sipo_out_len_next = (valid_o && ready_o) ? sipo_out_len - OUTPUT_CAPACITY : sipo_out_len;
        sipo_out_in = {sample2, sample1, sample0};
        samples = sipo_out[SAMPLE_W*BUS_W-1:0];
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            sipo_in      <= '0;
            sipo_out     <= '0;
            sipo_in_len  <= '0;
            sipo_out_len <= '0;
        end else begin
            sipo_in_len <= sipo_in_len_next - shift_in_amt[6:0];
            sipo_in <= sipo_in_shift |
                       (valid_i && ready_i ? ({{(80-W){1'b0}}, rdi} << (sipo_in_len - shift_in_amt[6:0])) : '0);

            case (num_valid)
                2'd1: sipo_out_len <= sipo_out_len_next + SAMPLE_BITS;
                2'd2: sipo_out_len <= sipo_out_len_next + 2 * SAMPLE_BITS;
                2'd3: sipo_out_len <= sipo_out_len_next + 3 * SAMPLE_BITS;
                default: sipo_out_len <= sipo_out_len_next;
            endcase

            if (valid_o && ready_o)
                sipo_out <= (sipo_out >> OUTPUT_CAPACITY) |
                            (num_valid != 0 ? ({{(138-3*SAMPLE_W){1'b0}}, sipo_out_in} << sipo_out_len_next) : '0);
            else if (num_valid != 0)
                sipo_out <= sipo_out | ({{(138-3*SAMPLE_W){1'b0}}, sipo_out_in} << sipo_out_len);
        end
    end
endmodule
