// Author: Nguyen Hung
// License: Apache-2.0
`timescale 1ns/1ps

module tb_gen_c;
    logic clk = 1'b0;
    logic start, rst, mode, valid_i, ready_i, valid_o, ready_o, ch_read, done_sampler;
    logic [2:0] sec_lvl;
    logic [63:0] seed_i, ch, din, dout;
    logic [91:0] samples;
    logic rst_k, src_ready, src_read, dst_write, dst_ready;

    gen_c dut (.*);
    always #5 clk = ~clk;

    initial begin
        rst = 1'b1; start = 1'b0; mode = 1'b0; sec_lvl = 3'd2; valid_i = 1'b0;
        seed_i = '0; ready_o = 1'b1; ch_read = 1'b0; dout = '0; src_read = 1'b0; dst_write = 1'b0;
        @(posedge clk); #1;
        rst = 1'b0;
        if (!rst_k) $fatal(1, "gen-C must reset Keccak while held");
        start = 1'b1;
        @(posedge clk); #1;
        start = 1'b0;
        for (int i = 0; i < 8; i++) begin
            valid_i = 1'b1;
            seed_i = 64'hC0 + i;
            #1;
            if (!ready_i) $fatal(1, "gen-C did not accept mu word %0d", i);
            @(posedge clk); #1;
        end
        valid_i = 1'b0;
        if (src_ready || din !== {32'he0000100, 32'd6656}) $fatal(1, "gen-C control block failed");
        $display("PASS: tb_gen_c");
        $finish;
    end
endmodule
