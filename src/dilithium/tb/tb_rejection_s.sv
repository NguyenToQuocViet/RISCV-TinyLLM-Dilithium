// Author: Luke Beckwith
// License: Apache-2.0
`timescale 1ns/1ps

module tb_rejection_s;
    logic clk = 1'b0;
    logic rst, valid_i, ready_i, valid_o, ready_o;
    logic [2:0] sec_lvl;
    logic [63:0] rdi;
    logic [91:0] samples;

    rejection_s dut (.*);
    always #5 clk = ~clk;

    initial begin
        rst = 1'b1;
        sec_lvl = 3'd3;
        valid_i = 1'b0;
        ready_o = 1'b0;
        rdi = '0;
        @(posedge clk); #1;
        rst = 1'b0;

        valid_i = 1'b1;
        rdi = 64'h00000000003210;
        @(posedge clk); #1;
        valid_i = 1'b0;
        repeat (2) @(posedge clk);
        #1;
        if (!valid_o || samples !== {23'd1, 23'd2, 23'd3, 23'd4})
            $fatal(1, "rejection-S centering or packing failed");
        $display("PASS: tb_rejection_s");
        $finish;
    end
endmodule
