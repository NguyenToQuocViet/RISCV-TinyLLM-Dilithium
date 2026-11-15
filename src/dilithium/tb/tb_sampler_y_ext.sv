// Author: Luke Beckwith
// License: Apache-2.0
`timescale 1ns/1ps

module tb_sampler_y_ext;
    logic clk = 1'b0;
    logic start, rst, valid_i, ready_i, valid_o, ready_o, done;
    logic [2:0] sec_lvl;
    logic [15:0] nonce;
    logic [63:0] seed_i, din, dout;
    logic [91:0] samples;
    logic rst_k, src_ready, src_read, dst_write, dst_ready;

    sampler_y_ext dut (.*);
    always #5 clk = ~clk;

    initial begin
        rst = 1'b1;
        start = 1'b0;
        sec_lvl = 3'd2;
        nonce = 16'h4321;
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
        if (din !== 64'hE00f000000000210) $fatal(1, "sampler-Y mode word failed");

        src_read = 1'b1;
        @(posedge clk); #1;
        src_read = 1'b0;
        for (int idx = 0; idx < 8; idx++) begin
            seed_i = 64'hC0 + 64'(idx);
            valid_i = 1'b1;
            #1;
            if (!ready_i) $fatal(1, "sampler-Y did not request seed word %0d", idx);
            @(posedge clk); #1;
        end
        valid_i = 1'b0;
        if (din !== 64'hC0) $fatal(1, "sampler-Y seed ordering failed");

        repeat (8) begin
            src_read = 1'b1;
            @(posedge clk); #1;
            src_read = 1'b0;
        end
        if (din !== {nonce[7:0], nonce[15:8], 48'd0}) $fatal(1, "sampler-Y nonce word failed");
        src_read = 1'b1;
        @(posedge clk); #1;
        src_read = 1'b0;
        if (!dst_ready || done) $fatal(1, "sampler-Y sampling interface failed");
        $display("PASS: tb_sampler_y_ext");
        $finish;
    end
endmodule
