// Author: Nguyen Hung
// License: Nguyen Hung
`timescale 1ns/1ps
module tb_zero_strip;
    logic [4:0] encode_lvl;
    logic [15:0] di;
    logic [31:0] dout;

    zero_strip #(.OUTPUT_W(4), .COEFF_W(4), .MAX_LVL(8)) dut (.*);

    initial begin
        di = 16'h4321; encode_lvl = 2;
        #1;
        if (dout !== 32'h00000139) $fatal(1, "packing failed");
        encode_lvl = 0;
        #1;
        if (dout !== 32'h00000007) $fatal(1, "zero shift failed");
        $display("PASS: tb_zero_strip");
        $finish;
    end
endmodule
