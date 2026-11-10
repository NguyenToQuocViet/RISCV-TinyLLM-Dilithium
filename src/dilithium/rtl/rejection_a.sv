// Author: Luke Beckwith
// License: Apache-2.0
`timescale 1ns/1ps

module rejection_a #(
    parameter int W            = 64,
    parameter int SAMPLE_W     = 23,
    parameter int RDI_SAMPLE_W = 24,
    parameter int BUS_W        = 4
) (
    input  logic                        rst,
    input  logic                        clk,
    input  logic                        valid_i,
    output logic                        ready_i,
    input  logic [W-1:0]                rdi,
    output logic [SAMPLE_W*BUS_W-1:0]   samples,
    output logic                        valid_o,
    input  logic                        ready_o
);
    localparam logic [22:0] DILITHIUM_Q = 23'd8380417;
    localparam logic [6:0] INPUT_CAPACITY = 7'(3 * RDI_SAMPLE_W);
    localparam logic [6:0] TWO_INPUT_SAMPLES = 7'(2 * RDI_SAMPLE_W);
    localparam logic [7:0] OUTPUT_CAPACITY = 8'(SAMPLE_W * BUS_W);
    localparam logic [7:0] SAMPLE_BITS = 8'(SAMPLE_W);

    logic [79:0] rdi_shift;
    logic [6:0] rdi_shift_amt;
    logic [79:0] sipo_in;
    logic [137:0] sipo_out;
    logic [3*SAMPLE_W-1:0] sipo_out_in;
    logic [6*SAMPLE_W-1:0] sipo_out_in_shift;
    logic [9:0] sipo_out_in_shift_amt;
    logic [22:0] rej_lane0, rej_lane1, rej_lane2;
    logic rej_lane0_valid, rej_lane1_valid, rej_lane2_valid;
    logic [1:0] num_valid;
    logic [6:0] sipo_in_len, sipo_in_len_next;
    logic [7:0] sipo_out_len, sipo_out_len_next;

    always_comb begin
        ready_i = sipo_in_len < INPUT_CAPACITY;
        valid_o = sipo_out_len >= OUTPUT_CAPACITY;

        rej_lane0 = sipo_in[22:0];
        rej_lane1 = sipo_in[46:24];
        rej_lane2 = sipo_in[70:48];
        rej_lane0_valid = rej_lane0 < DILITHIUM_Q && sipo_in_len >= RDI_SAMPLE_W[6:0];
        rej_lane1_valid = rej_lane1 < DILITHIUM_Q && sipo_in_len >= TWO_INPUT_SAMPLES;
        rej_lane2_valid = rej_lane2 < DILITHIUM_Q && sipo_in_len >= INPUT_CAPACITY;
        num_valid = rej_lane0_valid + rej_lane1_valid + rej_lane2_valid;

        if (!rej_lane0_valid) rej_lane0 = '0;
        if (!rej_lane1_valid) rej_lane1 = '0;
        if (!rej_lane2_valid) rej_lane2 = '0;

        unique case ({rej_lane2_valid, rej_lane1_valid, rej_lane0_valid})
            3'b111:  sipo_out_in = {rej_lane2, rej_lane1, rej_lane0};
            3'b101:  sipo_out_in = {23'd0, rej_lane2, rej_lane0};
            3'b110:  sipo_out_in = {23'd0, rej_lane2, rej_lane1};
            3'b100:  sipo_out_in = {46'd0, rej_lane2};
            3'b011:  sipo_out_in = {23'd0, rej_lane1, rej_lane0};
            3'b010:  sipo_out_in = {46'd0, rej_lane1};
            3'b001:  sipo_out_in = {46'd0, rej_lane0};
            default: sipo_out_in = '0;
        endcase

        if (sipo_in_len >= INPUT_CAPACITY)
            rdi_shift_amt = INPUT_CAPACITY;
        else if (sipo_in_len >= TWO_INPUT_SAMPLES)
            rdi_shift_amt = TWO_INPUT_SAMPLES;
        else
            rdi_shift_amt = '0;

        rdi_shift = {{(80-W){1'b0}}, rdi} << (sipo_in_len - rdi_shift_amt);
        sipo_in_len_next = (valid_i && ready_i) ? sipo_in_len + W[6:0] : sipo_in_len;
        sipo_out_len_next = (valid_o && ready_o) ? sipo_out_len - OUTPUT_CAPACITY : sipo_out_len;
        sipo_out_in_shift_amt = valid_o ? {2'd0, sipo_out_len_next} : {2'd0, sipo_out_len};
        sipo_out_in_shift = {{(3*SAMPLE_W){1'b0}}, sipo_out_in} << sipo_out_in_shift_amt;
        samples = sipo_out[OUTPUT_CAPACITY-1:0];
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            sipo_in       <= '0;
            sipo_out      <= '0;
            sipo_in_len   <= '0;
            sipo_out_len  <= '0;
        end else begin
            sipo_in_len <= sipo_in_len_next - rdi_shift_amt;
            if (sipo_in_len >= INPUT_CAPACITY)
                sipo_in <= (sipo_in >> INPUT_CAPACITY) | (valid_i && ready_i ? rdi_shift : '0);
            else if (sipo_in_len >= TWO_INPUT_SAMPLES)
                sipo_in <= (sipo_in >> TWO_INPUT_SAMPLES) | (valid_i && ready_i ? rdi_shift : '0);
            else if (valid_i && ready_i)
                sipo_in <= sipo_in | rdi_shift;

            case (num_valid)
                2'd1: sipo_out_len <= sipo_out_len_next + SAMPLE_BITS;
                2'd2: sipo_out_len <= sipo_out_len_next + 2 * SAMPLE_BITS;
                2'd3: sipo_out_len <= sipo_out_len_next + 3 * SAMPLE_BITS;
                default: sipo_out_len <= sipo_out_len_next;
            endcase

            if (valid_o && ready_o)
                sipo_out <= (sipo_out >> OUTPUT_CAPACITY) |
                            (num_valid != 0 ? sipo_out_in_shift : '0);
            else if (num_valid != 0)
                sipo_out <= sipo_out | sipo_out_in_shift;
        end
    end
endmodule
