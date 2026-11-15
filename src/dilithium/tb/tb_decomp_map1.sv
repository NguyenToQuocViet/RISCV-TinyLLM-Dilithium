// Author: Nguyen Hung
// License: Nguyen Hung
`timescale 1ns/1ps
module tb_decomp_map1;
    logic [2:0] sec_lvl;
    logic [22:0] din;
    logic [5:0] dout;

    decomp_map1 dut (.*);

    initial begin
        sec_lvl = 3'd2;
        din = 23'd0;
        #1;
        if (dout !== 6'd0) $fatal(1, "level-2 lower range failed");
        din = 23'd95233;
        #1;
        if (dout !== 6'd1) $fatal(1, "level-2 threshold failed");
        din = 23'd8285185;
        #1;
        if (dout !== 6'd0) $fatal(1, "level-2 wrap threshold failed");
        sec_lvl = 3'd3;
        din = 23'd261889;
        #1;
        if (dout !== 6'd1) $fatal(1, "level-3 threshold failed");
        din = 23'd8118529;
        #1;
        if (dout !== 6'd0) $fatal(1, "level-3 wrap threshold failed");
        $display("PASS: tb_decomp_map1");
        $finish;
    end
endmodule
