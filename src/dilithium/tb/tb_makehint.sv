// Author: Luke Beckwith
// License: Apache-2.0
`timescale 1ns/1ps

module tb_makehint;
    logic clk = 1'b0;
    logic rst, reject_hint, poly_valid_ie, poly_ready_i, hint_valid_o, hint_ready_o;
    logic [2:0] sec_lvl;
    logic [95:0] poly0_ie, poly1_ie;
    logic [63:0] hint_o;

    makehint dut (.*);
    always #5 clk = ~clk;

    initial begin
        rst = 1'b1; sec_lvl = 3'd2; poly_valid_ie = 1'b0; hint_ready_o = 1'b0;
        poly0_ie = '0; poly1_ie = '0;
        @(posedge clk); #1;
        rst = 1'b0;
        if (!poly_ready_i || reject_hint) $fatal(1, "makehint reset interface failed");
        poly0_ie = {4{24'd95233}};
        poly_valid_ie = 1'b1;
        @(posedge clk); #1;
        poly_valid_ie = 1'b0;
        @(posedge clk); #1;
        if (dut.num_hints != 4 || dut.hint_addr[0] != 0 || dut.hint_addr[3] != 3)
            $fatal(1, "makehint address collection failed");
        $display("PASS: tb_makehint");
        $finish;
    end
endmodule
