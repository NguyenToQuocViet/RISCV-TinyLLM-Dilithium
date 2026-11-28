// Author: Nguyen Hung
// License: Apache-2.0
`timescale 1ns/1ps

module tb_sampler_s;
    logic clk = 1'b0;
    logic start, rst, re_sample, valid_i, ready_i, valid_o, ready_o, done;
    logic [2:0] sec_lvl;
    logic [15:0] n;
    logic [63:0] seed_i, din, dout;
    logic [91:0] samples;
    logic keccak_ctrl, rst_k, src_ready, src_read, dst_write, dst_ready;

    sampler_s dut (.*);
    always #5 clk = ~clk;

    initial begin
        rst = 1'b1;
        start = 1'b0;
        re_sample = 1'b0;
        sec_lvl = 3'd2;
        n = 16'h1234;
        valid_i = 1'b0;
        ready_o = 1'b1;
        seed_i = '0;
        dout = '0;
        keccak_ctrl = 1'b0;
        src_read = 1'b0;
        dst_write = 1'b0;
        @(posedge clk); #1;
        rst = 1'b0;
        start = 1'b1;
        @(posedge clk); #1;
        start = 1'b0;

        for (int idx = 0; idx < 8; idx++) begin
            if (!ready_i) $fatal(1, "sampler-S did not request seed word %0d", idx);
            seed_i = 64'hB0 + 64'(idx);
            valid_i = 1'b1;
            @(posedge clk); #1;
        end
        valid_i = 1'b0;
        keccak_ctrl = 1'b1;
        @(posedge clk); #1;
        keccak_ctrl = 1'b0;
        if (din !== 64'hE00f000000000210) $fatal(1, "sampler-S mode word failed");

        src_read = 1'b1;
        @(posedge clk); #1;
        src_read = 1'b0;
        if (din !== 64'hB0) $fatal(1, "sampler-S seed ordering failed");
        repeat (8) begin
            src_read = 1'b1;
            @(posedge clk); #1;
            src_read = 1'b0;
        end
        if (din !== {n[7:0], n[15:8], 48'd0}) $fatal(1, "sampler-S nonce word failed");
        src_read = 1'b1;
        @(posedge clk); #1;
        src_read = 1'b0;
        if (done) $fatal(1, "sampler-S ended before sample output");
        $display("PASS: tb_sampler_s");
        $finish;
    end
endmodule
