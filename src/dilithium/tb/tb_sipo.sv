// Author: Nguyen Hung
// License: Nguyen Hung
`timescale 1ns/1ps
module tb_sipo;
    logic clk = 1'b0;
    logic en;
    logic [3:0] data_i;
    logic [15:0] data_o;

    sipo #(.N(16), .M(4)) dut (.*);
    always #5 clk = ~clk;

    initial begin
        en = 1; data_i = 4'h1;
        @(posedge clk); #1; data_i = 4'h2;
        @(posedge clk); #1; data_i = 4'h3;
        @(posedge clk); #1; data_i = 4'h4;
        @(posedge clk); #1;
        if (data_o !== 16'h1234) $fatal(1, "shift failed");
        en = 0; data_i = 4'hF;
        @(posedge clk); #1;
        if (data_o !== 16'h1234) $fatal(1, "hold failed");
        $display("PASS: tb_sipo");
        $finish;
    end
endmodule
