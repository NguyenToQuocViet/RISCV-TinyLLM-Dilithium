// Author: Luke Beckwith
// License: Apache-2.0
`timescale 1ns/1ps

module rejection_s #(
    parameter int W            = 64,
    parameter int RDI_SAMPLE_W = 4,
    parameter int SAMPLE_W     = 23,
    parameter int BUS_W        = 4
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
    localparam logic [4:0] ETA2_LIMIT = 5'd15;
    localparam logic [4:0] ETA4_LIMIT = 5'd9;
    localparam logic [6:0] INPUT_CAPACITY = 7'(3 * RDI_SAMPLE_W);
    localparam logic [6:0] TWO_INPUT_SAMPLES = 7'(2 * RDI_SAMPLE_W);
    localparam logic [7:0] OUTPUT_CAPACITY = 8'(SAMPLE_W * BUS_W);
    localparam logic [7:0] SAMPLE_BITS = 8'(SAMPLE_W);

    logic [4:0] eta_limit;
    logic [79:0] sipo_in, sipo_in_shift;
    logic [199:0] sipo_out;
    logic [3*SAMPLE_W-1:0] sipo_out_in;
    logic [6:0] shift_amt;
    logic [3:0] rej_lane0, rej_lane1, rej_lane2;
    logic [3:0] rej_lane0_map, rej_lane1_map, rej_lane2_map;
    logic [22:0] sample0, sample1, sample2;
    logic rej_lane0_valid, rej_lane1_valid, rej_lane2_valid;
    logic [1:0] num_valid;
    logic [6:0] sipo_in_len, sipo_in_len_next;
    logic [7:0] sipo_out_len, sipo_out_len_next;

    function automatic logic [3:0] eta2_map(input logic [3:0] lane);
        if (lane < 5)       eta2_map = lane;
        else if (lane < 10) eta2_map = lane - 4'd5;
        else                eta2_map = lane - 4'd10;
    endfunction

    function automatic logic [22:0] centered_sample(
        input logic [3:0] lane,
        input logic [3:0] eta
    );
        centered_sample = (lane > eta) ? DILITHIUM_Q + {19'd0, eta} - {19'd0, lane} :
                                         {19'd0, eta} - {19'd0, lane};
    endfunction

    always_comb begin
        eta_limit = (sec_lvl == 3'd3) ? ETA4_LIMIT : ETA2_LIMIT;
        ready_i = sipo_in_len < INPUT_CAPACITY;
        valid_o = sipo_out_len >= OUTPUT_CAPACITY;
        rej_lane0 = sipo_in[3:0];
        rej_lane1 = sipo_in[7:4];
        rej_lane2 = sipo_in[11:8];

        if (sec_lvl == 3'd3) begin
            rej_lane0_map = rej_lane0;
            rej_lane1_map = rej_lane1;
            rej_lane2_map = rej_lane2;
            sample0 = centered_sample(rej_lane0, 4'd4);
            sample1 = centered_sample(rej_lane1, 4'd4);
            sample2 = centered_sample(rej_lane2, 4'd4);
        end else begin
            rej_lane0_map = eta2_map(rej_lane0);
            rej_lane1_map = eta2_map(rej_lane1);
            rej_lane2_map = eta2_map(rej_lane2);
            sample0 = centered_sample(rej_lane0_map, 4'd2);
            sample1 = centered_sample(rej_lane1_map, 4'd2);
            sample2 = centered_sample(rej_lane2_map, 4'd2);
        end

        rej_lane0_valid = {1'b0, rej_lane0} < eta_limit && sipo_in_len >= RDI_SAMPLE_W[6:0];
        rej_lane1_valid = {1'b0, rej_lane1} < eta_limit && sipo_in_len >= TWO_INPUT_SAMPLES;
        rej_lane2_valid = {1'b0, rej_lane2} < eta_limit && sipo_in_len >= INPUT_CAPACITY;
        num_valid = rej_lane0_valid + rej_lane1_valid + rej_lane2_valid;
        if (!rej_lane0_valid) sample0 = '0;
        if (!rej_lane1_valid) sample1 = '0;
        if (!rej_lane2_valid) sample2 = '0;

        unique case ({rej_lane2_valid, rej_lane1_valid, rej_lane0_valid})
            3'b111:  sipo_out_in = {sample2, sample1, sample0};
            3'b101:  sipo_out_in = {23'd0, sample2, sample0};
            3'b110:  sipo_out_in = {23'd0, sample2, sample1};
            3'b100:  sipo_out_in = {46'd0, sample2};
            3'b011:  sipo_out_in = {23'd0, sample1, sample0};
            3'b010:  sipo_out_in = {46'd0, sample1};
            3'b001:  sipo_out_in = {46'd0, sample0};
            default: sipo_out_in = '0;
        endcase

        if (sipo_in_len >= INPUT_CAPACITY)
            shift_amt = INPUT_CAPACITY;
        else if (sipo_in_len >= TWO_INPUT_SAMPLES)
            shift_amt = TWO_INPUT_SAMPLES;
        else if (sipo_in_len >= RDI_SAMPLE_W[6:0])
            shift_amt = RDI_SAMPLE_W[6:0];
        else
            shift_amt = '0;

        sipo_in_shift = sipo_in >> shift_amt;
        sipo_in_len_next = (valid_i && ready_i) ? sipo_in_len + W[6:0] : sipo_in_len;
        sipo_out_len_next = (valid_o && ready_o) ? sipo_out_len - OUTPUT_CAPACITY : sipo_out_len;
        samples = sipo_out[OUTPUT_CAPACITY-1:0];
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            sipo_in      <= '0;
            sipo_out     <= '0;
            sipo_in_len  <= '0;
            sipo_out_len <= '0;
        end else begin
            sipo_in_len <= sipo_in_len_next - shift_amt;
            sipo_in <= sipo_in_shift |
                       (valid_i && ready_i ? ({{(80-W){1'b0}}, rdi} << (sipo_in_len - shift_amt)) : '0);

            case (num_valid)
                2'd1: sipo_out_len <= sipo_out_len_next + SAMPLE_BITS;
                2'd2: sipo_out_len <= sipo_out_len_next + 2 * SAMPLE_BITS;
                2'd3: sipo_out_len <= sipo_out_len_next + 3 * SAMPLE_BITS;
                default: sipo_out_len <= sipo_out_len_next;
            endcase

            if (valid_o && ready_o)
                sipo_out <= (sipo_out >> OUTPUT_CAPACITY) |
                            (num_valid != 0 ? ({{(200-3*SAMPLE_W){1'b0}}, sipo_out_in} << sipo_out_len_next) : '0);
            else if (num_valid != 0)
                sipo_out <= sipo_out | ({{(200-3*SAMPLE_W){1'b0}}, sipo_out_in} << sipo_out_len);
        end
    end
endmodule
