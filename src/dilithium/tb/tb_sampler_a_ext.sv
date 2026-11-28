// Author: Nguyen Hung
// License: Apache-2.0
`timescale 1ns/1ps

module tb_sampler_a_ext;
    logic clk = 1'b0;
    logic start, rst, re_sample, valid_i, ready_i, valid_o, ready_o, done;
    logic [3:0] i, j;
    logic [63:0] seed_i, din, dout;
    logic rst_k, src_ready, src_read, dst_write, dst_ready;
    logic [91:0] samples;

    sampler_a_ext dut (.*);
    always #5 clk = ~clk;

    initial begin
        rst = 1'b1;
        start = 1'b0;
        re_sample = 1'b0;
        i = 4'd2;
        j = 4'd3;
        valid_i = 1'b0;
        ready_o = 1'b1;
        seed_i = '0;
        dout = '0;
        src_read = 1'b0;
        dst_write = 1'b0;
        @(posedge clk); #1;
        rst = 1'b0;
        start = 1'b1;
        @(posedge clk); #1;
        start = 1'b0;
        if (din !== 64'hC00f000000000110) $fatal(1, "sampler-A mode word failed");

        src_read = 1'b1;
        @(posedge clk); #1;
        src_read = 1'b0;
        for (int n = 0; n < 4; n++) begin
            if (!ready_i) $fatal(1, "sampler-A did not request seed word %0d", n);
            seed_i = 64'hA0 + 64'(n);
            valid_i = 1'b1;
            @(posedge clk); #1;
        end
        valid_i = 1'b0;
        if (din !== 64'hA0) $fatal(1, "sampler-A seed ordering failed");

        repeat (4) begin
            src_read = 1'b1;
            @(posedge clk); #1;
            src_read = 1'b0;
        end
        if (din !== {4'd0, j, 4'd0, i, 48'd0}) $fatal(1, "sampler-A nonce word failed");
        src_read = 1'b1;
        @(posedge clk); #1;
        src_read = 1'b0;
        if (!dst_ready || done) $fatal(1, "sampler-A sampling interface failed");
        $display("PASS: tb_sampler_a_ext");
        $finish;
    end
endmodule
