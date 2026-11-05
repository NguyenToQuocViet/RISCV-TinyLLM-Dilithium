// Author: Nguyen Hung
// License: Nguyen Hung
`timescale 1ns/1ps
module tb_uncenter_coeff;
    logic [2:0] sec_lvl, mode;
    logic [22:0] di, dout;

    uncenter_coeff dut (.*);

    initial begin
        sec_lvl = 3; mode = 0; di = 23'd100;
        #1;
        if (dout !== 23'd100) $fatal(1, "none failed");
        mode = 1; di = 23'd6;
        #1;
        if (dout !== 23'd8380415) $fatal(1, "eta failed");
        mode = 2; di = 23'd5000;
        #1;
        if (dout !== 23'd3192) $fatal(1, "t0 failed");
        mode = 3;
        #1;
        if (dout !== 23'd1) $fatal(1, "t1 failed");
        sec_lvl = 2; mode = 4; di = 23'd131073;
        #1;
        if (dout !== 23'd8380416) $fatal(1, "gamma1 failed");
        $display("PASS: tb_uncenter_coeff");
        $finish;
    end
endmodule
