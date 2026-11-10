// Author: Luke Beckwith
// License: Apache-2.0
`timescale 1ns/1ps

module tb_rejection_y;
    logic clk = 1'b0;
    logic rst, valid_i, ready_i, valid_o, ready_o;
    logic [2:0] sec_lvl;
    logic [63:0] rdi;
    logic [91:0] samples;

    rejection_y dut (.*);
    always #5 clk = ~clk;

    initial begin
        rst = 1'b1;
        sec_lvl = 3'd2;
        valid_i = 1'b0;
        ready_o = 1'b0;
        rdi = '0;
        @(posedge clk); #1;
        rst = 1'b0;

        valid_i = 1'b1;
        rdi = (64'd3 << 54) | (64'd2 << 36) | (64'd1 << 18);
        @(posedge clk); #1;
        valid_i = 1'b0;
        @(posedge clk); #1;
        if (!ready_i) $fatal(1, "rejection-Y input flow control failed");
        valid_i = 1'b1;
        rdi = '0;
        @(posedge clk); #1;
        valid_i = 1'b0;
        @(posedge clk); #1;
        if (!valid_o || samples !== {23'd131069, 23'd131070, 23'd131071, 23'd131072}) begin
            $fatal(1, "rejection-Y centering or packing failed");
        end
        $display("PASS: tb_rejection_y");
        $finish;
    end
endmodule
