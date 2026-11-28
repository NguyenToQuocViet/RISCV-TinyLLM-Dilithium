// Author: Nguyen Hung
// License: Apache-2.0
`timescale 1ns/1ps

module tb_usehint;
    logic clk = 1'b0;
    logic rst, start, valid_i, ready_i, poly_valid_i, poly_ready_i, poly_valid_o, poly_ready_o;
    logic [2:0] sec_lvl;
    logic [63:0] di;
    logic [95:0] poly0_i, poly1_i, poly_o;

    usehint dut (.*);
    always #5 clk = ~clk;

    initial begin
        rst = 1'b1; start = 1'b0; sec_lvl = 3'd2; valid_i = 1'b0; di = '0;
        poly0_i = '0; poly1_i = {4{24'd1}}; poly_valid_i = 1'b0; poly_ready_o = 1'b1;
        @(posedge clk); #1;
        rst = 1'b0;
        start = 1'b1;
        @(posedge clk); #1;
        start = 1'b0;
        for (int i = 0; i < 11; i++) begin
            valid_i = 1'b1;
            di = '0;
            #1;
            if (!ready_i) $fatal(1, "usehint did not accept hint word %0d", i);
            @(posedge clk); #1;
        end
        valid_i = 1'b0;
        @(posedge clk); #1;
        poly_valid_i = 1'b1;
        #1;
        if (!poly_valid_o || poly_o !== poly1_i) $fatal(1, "usehint zero-hint application failed");
        $display("PASS: tb_usehint");
        $finish;
    end
endmodule
