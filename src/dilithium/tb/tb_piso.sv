// Author: Nguyen Hung
// License: Nguyen Hung
`timescale 1ns/1ps
module tb_piso;
    logic clk = 1'b0;
    logic en, sel;
    logic [15:0] data_i;
    logic [3:0] data_o;

    piso #(.N(16), .M(4)) dut (.*);
    always #5 clk = ~clk;

    initial begin
        en = 1; sel = 1; data_i = 16'hABCD;
        @(posedge clk); #1;
        if (data_o !== 4'hA) $fatal(1, "load failed");
        sel = 0; data_i = '0;
        @(posedge clk); #1;
        if (data_o !== 4'hB) $fatal(1, "first shift failed");
        @(posedge clk); #1;
        if (data_o !== 4'hC) $fatal(1, "second shift failed");
        @(posedge clk); #1;
        if (data_o !== 4'hD) $fatal(1, "third shift failed");
        $display("PASS: tb_piso");
        $finish;
    end
endmodule
