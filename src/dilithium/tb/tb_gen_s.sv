// Author: Nguyen Hung
// License: Apache-2.0
`timescale 1ns/1ps

module tb_gen_s;
    logic clk = 1'b0;
    logic start, rst, valid_seed, ready_for_seed, done_sampler, keccak_ctrl;
    logic [2:0] sec_lvl;
    logic [63:0] seed_i, din, dout;
    logic [91:0] samples;
    logic valid_o, ready_o, rst_k, src_ready, src_read, dst_write, dst_ready;

    gen_s dut (.*);
    always #5 clk = ~clk;

    initial begin
        rst = 1'b1; start = 1'b0; valid_seed = 1'b0; sec_lvl = 3'd2;
        seed_i = '0; ready_o = 1'b1; keccak_ctrl = 1'b0; src_read = 1'b0; dst_write = 1'b0; dout = '0;
        @(posedge clk); #1;
        rst = 1'b0;
        start = 1'b1;
        @(posedge clk); #1;
        start = 1'b0;
        @(posedge clk); #1;
        if (!ready_for_seed) $fatal(1, "sampler-S did not request its seed");
        for (int i = 0; i < 8; i++) begin
            valid_seed = 1'b1;
            seed_i = 64'hB0 + i;
            @(posedge clk); #1;
        end
        valid_seed = 1'b0;
        keccak_ctrl = 1'b1;
        @(posedge clk); #1;
        keccak_ctrl = 1'b0;
        if (din !== 64'hE00f000000000210) $fatal(1, "sampler-S mode word failed");
        $display("PASS: tb_gen_s");
        $finish;
    end
endmodule
