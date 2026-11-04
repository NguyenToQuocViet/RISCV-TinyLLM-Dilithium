// Author: Nguyen Hung
// License: Nguyen Hung
`timescale 1ns/1ps
module tb_regn;
    logic clk = 1'b0;
    logic rst, en;
    logic [7:0] data_i, data_o;

    regn #(.N(8), .INIT(8'hA5)) dut (.*);
    always #5 clk = ~clk;

    initial begin
        rst = 1; en = 0; data_i = '0;
        @(posedge clk); #1;
        if (data_o !== 8'hA5) $fatal(1, "reset failed");
        rst = 0; en = 1; data_i = 8'h3C;
        @(posedge clk); #1;
        if (data_o !== 8'h3C) $fatal(1, "load failed");
        en = 0; data_i = 8'hF0;
        @(posedge clk); #1;
        if (data_o !== 8'h3C) $fatal(1, "hold failed");
        $display("PASS: tb_regn");
        $finish;
    end
endmodule
