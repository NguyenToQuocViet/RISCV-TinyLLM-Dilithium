// Author: Nguyen Hung
// License: Apache-2.0
`timescale 1ns/1ps

module gen_a_ext #(
    parameter int SAMPLER_NUM = 2,
    parameter int SAMPLER_W   = 4,
    parameter int SAMPLE_W    = 23,
    parameter int W           = 64
) (
    input  logic                                  start,
    input  logic                                  rst,
    input  logic                                  clk,
    input  logic [2:0]                            sec_lvl,
    input  logic                                  valid_seed,
    output logic                                  ready_for_seed,
    input  logic [W-1:0]                          seed_i,
    output logic [SAMPLER_NUM*SAMPLER_W*SAMPLE_W-1:0] samples,
    output logic [5:0]                            sample_state_out,
    output logic [SAMPLER_NUM-1:0]                valid_o,
    input  logic [SAMPLER_NUM-1:0]                ready_o,
    output logic                                  done_sampler,
    output logic [SAMPLER_NUM-1:0]                rst_k,
    output logic [SAMPLER_NUM*64-1:0]             din,
    input  logic [SAMPLER_NUM*64-1:0]             dout,
    output logic [SAMPLER_NUM-1:0]                src_ready,
    input  logic [SAMPLER_NUM-1:0]                src_read,
    input  logic [SAMPLER_NUM-1:0]                dst_write,
    output logic [SAMPLER_NUM-1:0]                dst_ready
);
    logic [3:0] k_index [0:SAMPLER_NUM-1];
    logic [3:0] l_index [0:SAMPLER_NUM-1];
    logic [SAMPLER_NUM-1:0] ready_i, done, re_sample, done_latch;
    logic [5:0] sample_state;
    int matrix_l;
    int final_state;

    assign sample_state_out = sample_state;
    assign ready_for_seed = &ready_i;

    generate
        for (genvar g = 0; g < SAMPLER_NUM; g++) begin : samplers
            sampler_a_ext #(.W(W), .SAMPLE_W(SAMPLE_W), .BUS_W(SAMPLER_W)) sampler_a (
                .start, .rst, .clk, .re_sample(re_sample[g]), .i(k_index[g]), .j(l_index[g]),
                .valid_i(valid_seed), .ready_i(ready_i[g]), .seed_i,
                .samples(samples[g*SAMPLER_W*SAMPLE_W +: SAMPLER_W*SAMPLE_W]),
                .valid_o(valid_o[g]), .ready_o(ready_o[g]), .done(done[g]),
                .rst_k(rst_k[g]), .din(din[g*64 +: 64]), .dout(dout[g*64 +: 64]),
                .src_ready(src_ready[g]), .src_read(src_read[g]), .dst_write(dst_write[g]), .dst_ready(dst_ready[g])
            );
        end
    endgenerate

    always_comb begin
        case (sec_lvl)
            3'd2: begin matrix_l = 4; final_state = 14; end
            3'd3: begin matrix_l = 5; final_state = 28; end
            default: begin matrix_l = 7; final_state = 54; end
        endcase
        for (int i = 0; i < SAMPLER_NUM; i++) begin
            k_index[i] = (sample_state + i) / matrix_l;
            l_index[i] = (sample_state + i) % matrix_l;
        end
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            done_sampler <= 1'b0;
            done_latch <= '0;
            re_sample <= '0;
            sample_state <= '0;
        end else begin
            done_latch <= done_latch | done;
            done_sampler <= 1'b0;
            re_sample <= '0;
            if (done_latch == {SAMPLER_NUM{1'b1}}) begin
                done_latch <= '0;
                if (sample_state == final_state) begin
                    done_sampler <= 1'b1;
                    sample_state <= '0;
                end else begin
                    re_sample <= '1;
                    sample_state <= sample_state + SAMPLER_NUM;
                end
            end
        end
    end
endmodule
