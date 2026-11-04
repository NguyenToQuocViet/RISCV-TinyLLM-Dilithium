// Author: Nguyen Hung
// License: Nguyen Hung
`timescale 1ns/1ps
module tb_norm_check;
    logic [2:0] sec_lvl;
    logic [1:0] mode;
    logic validi, rej;
    logic [95:0] di;

    norm_check dut (.*);

    initial begin
        sec_lvl = 2; mode = 2; validi = 1; di = '0;
        #1;
        if (rej !== 1'b0) $fatal(1, "lower bound failed");
        di[23:0] = 24'd100000;
        #1;
        if (rej !== 1'b1) $fatal(1, "g2 failed");
        validi = 0;
        #1;
        if (rej !== 1'b0) $fatal(1, "valid gate failed");
        sec_lvl = 3; mode = 1; validi = 1; di = '0;
        di[47:24] = 24'd524092;
        #1;
        if (rej !== 1'b1) $fatal(1, "g1-beta failed");
        $display("PASS: tb_norm_check");
        $finish;
    end
endmodule
