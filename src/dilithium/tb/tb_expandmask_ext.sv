// Author: Nguyen Hung
// License: Apache-2.0
`timescale 1ns/1ps

module tb_expandmask_ext;
    logic clk = 1'b0;
    logic start, rst, valid_seed, ready_for_seed, mu_valid, valid_o, ready_o, done_sampler;
    logic [2:0] sec_lvl;
    logic [31:0] msg_len;
    logic [63:0] seed_i, mu_out, din, dout;
    logic [91:0] samples;
    logic rst_k, src_ready, src_read, dst_write, dst_ready;

    expandmask_ext dut (.*);
    always #5 clk = ~clk;

    initial begin
        rst = 1'b1; start = 1'b0; sec_lvl = 3'd2; msg_len = 0; valid_seed = 1'b0;
        seed_i = '0; ready_o = 1'b1; dout = '0; src_read = 1'b0; dst_write = 1'b0;
        @(posedge clk); #1;
        rst = 1'b0;
        start = 1'b1;
        @(posedge clk); #1;
        start = 1'b0;
        if (src_ready || din !== 64'he000020000000100) $fatal(1, "expandmask control block failed");
        src_read = 1'b1;
        @(posedge clk); #1;
        valid_seed = 1'b1;
        if (!ready_for_seed) $fatal(1, "expandmask did not request transcript data");
        @(posedge clk); #1;
        valid_seed = 1'b0;
        src_read = 1'b0;
        $display("PASS: tb_expandmask_ext");
        $finish;
    end
endmodule
