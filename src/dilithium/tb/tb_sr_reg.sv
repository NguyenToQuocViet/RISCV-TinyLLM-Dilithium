// Author: Nguyen Hung
// License: Nguyen Hung
`timescale 1ns/1ps
module tb_sr_reg;
    logic clk = 1'b0;
    logic rst, set, clr, q;

    sr_reg #(.INIT(1'b1)) dut (.*);
    always #5 clk = ~clk;

    initial begin
        rst = 1; set = 0; clr = 0;
        @(posedge clk); #1;
        if (q !== 1'b1) $fatal(1, "reset failed");
        rst = 0; clr = 1;
        @(posedge clk); #1;
        if (q !== 1'b0) $fatal(1, "clear failed");
        clr = 0; set = 1;
        @(posedge clk); #1;
        if (q !== 1'b1) $fatal(1, "set failed");
        $display("PASS: tb_sr_reg");
        $finish;
    end
endmodule
