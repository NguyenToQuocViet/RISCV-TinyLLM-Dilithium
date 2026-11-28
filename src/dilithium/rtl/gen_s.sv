// Author: Nguyen Hung
// License: Apache-2.0
`timescale 1ns/1ps

module gen_s #(
    parameter int SAMPLER_NUM = 1,
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
    output logic [SAMPLER_NUM-1:0]                valid_o,
    input  logic [SAMPLER_NUM-1:0]                ready_o,
    output logic                                  done_sampler,
    input  logic                                  keccak_ctrl,
    output logic                                  rst_k,
    output logic [63:0]                           din,
    input  logic [63:0]                           dout,
    output logic                                  src_ready,
    input  logic                                  src_read,
    input  logic                                  dst_write,
    output logic                                  dst_ready
);
    logic [15:0] nonce [0:SAMPLER_NUM-1];
    logic [SAMPLER_NUM-1:0] ready_i, done, re_sample, done_latch;
    logic [SAMPLER_NUM-1:0] valid_seed_bus;
    logic [4:0] sample_state;
    logic mode;
    logic [3:0] l_count, k_count;
    logic start_s;

    assign ready_for_seed = &ready_i;
    generate
        for (genvar g = 0; g < SAMPLER_NUM; g++) begin : samplers
            sampler_s #(.W(W), .SAMPLE_W(SAMPLE_W), .BUS_W(SAMPLER_W)) sampler_s_i (
                .start(start_s), .rst, .clk, .re_sample(re_sample[g]), .sec_lvl, .n(nonce[g]),
                .valid_i(valid_seed), .ready_i(ready_i[g]), .seed_i,
                .samples(samples[g*SAMPLER_W*SAMPLE_W +: SAMPLER_W*SAMPLE_W]),
                .valid_o(valid_o[g]), .ready_o(ready_o[g]), .done(done[g]), .keccak_ctrl,
                .rst_k, .din, .dout, .src_ready, .src_read, .dst_write, .dst_ready
            );
        end
    endgenerate

    always_comb begin
        case (sec_lvl)
            3'd2: begin l_count = 4; k_count = 4; end
            3'd3: begin l_count = 5; k_count = 6; end
            default: begin l_count = 7; k_count = 8; end
        endcase
        for (int i = 0; i < SAMPLER_NUM; i++)
            nonce[i] = mode ? sample_state + l_count : sample_state;
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            done_sampler <= 1'b0;
            done_latch <= '0;
            re_sample <= '0;
            sample_state <= '0;
            mode <= 1'b0;
            start_s <= 1'b0;
        end else begin
            done_latch <= done_latch | done;
            done_sampler <= 1'b0;
            re_sample <= '0;
            start_s <= !mode && start;
            if (mode && start)
                re_sample <= '1;
            if (done_latch == {SAMPLER_NUM{1'b1}}) begin
                done_latch <= '0;
                if ((!mode && sample_state == l_count - 1) || (mode && sample_state == k_count - 1)) begin
                    done_sampler <= 1'b1;
                    sample_state <= '0;
                    mode <= !mode;
                    if (!mode)
                        re_sample <= '1;
                end else begin
                    sample_state <= sample_state + 1'b1;
                    re_sample <= '1;
                end
            end
        end
    end
endmodule
