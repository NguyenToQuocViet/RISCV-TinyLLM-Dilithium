// Author: Nguyen Hung
// License: Apache-2.0
`timescale 1ns/1ps

module tb_gen_a_ext;
    logic clk = 1'b0;
    logic start, rst, valid_seed, ready_for_seed, done_sampler;
    logic [2:0] sec_lvl;
    logic [63:0] seed_i;
    logic [183:0] samples;
    logic [5:0] sample_state_out;
    logic [1:0] valid_o, ready_o, rst_k, src_ready, src_read, dst_write, dst_ready;
    logic [127:0] din, dout;

    gen_a_ext dut (.*);
    always #5 clk = ~clk;

    initial begin
        rst = 1'b1; start = 1'b0; valid_seed = 1'b0; sec_lvl = 3'd2;
        seed_i = '0; ready_o = '1; src_read = '0; dst_write = '0; dout = '0;
        @(posedge clk); #1;
        rst = 1'b0;
        start = 1'b1;
        @(posedge clk); #1;
        start = 1'b0;
        src_read = '1;
        @(posedge clk); #1;
        src_read = '0;
        if (!ready_for_seed || sample_state_out != 0) $fatal(1, "sampler-A group did not request its seed");
        for (int i = 0; i < 4; i++) begin
            valid_seed = 1'b1;
            seed_i = 64'hA0 + i;
            @(posedge clk); #1;
        end
        valid_seed = 1'b0;
        if (din[63:0] !== 64'hA0 || din[127:64] !== 64'hA0)
            $fatal(1, "sampler-A seed distribution failed");
        $display("PASS: tb_gen_a_ext");
        $finish;
    end
endmodule
