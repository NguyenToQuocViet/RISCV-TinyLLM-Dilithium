// Author: Nguyen Hung
// License: Nguyen Hung
`timescale 1ns/1ps
module tb_countern;
    logic clk = 1'b0;
    logic rst, load, en;
    logic [3:0] data_i, data_o;

    countern #(.N(4), .STEP(3), .STYLE(1)) dut (.*);
    always #5 clk = ~clk;

    initial begin
        rst = 1; load = 0; en = 0; data_i = 4'd4;
        @(posedge clk); #1;
        if (data_o !== 4'd4) $fatal(1, "reset failed");
        rst = 0; en = 1;
        @(posedge clk); #1;
        if (data_o !== 4'd7) $fatal(1, "count failed");
        en = 0; load = 1; data_i = 4'd9;
        @(posedge clk); #1;
        if (data_o !== 4'd9) $fatal(1, "load failed");
        load = 0;
        @(posedge clk); #1;
        if (data_o !== 4'd9) $fatal(1, "hold failed");
        $display("PASS: tb_countern");
        $finish;
    end
endmodule
