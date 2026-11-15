// Author: Nguyen Hung
// License: Nguyen Hung
`timescale 1ns/1ps
module tb_decoder;
    logic clk = 1'b0;
    logic rst, valid_i, ready_i, valid_o, ready_o;
    logic [2:0] sec_lvl, encode_modei;
    logic [63:0] di;
    logic [91:0] samples;

    decoder dut (.*);
    always #5 clk = ~clk;

    initial begin
        rst = 1'b1;
        sec_lvl = 3'd2;
        encode_modei = 3'd4;
        valid_i = 1'b0;
        ready_o = 1'b1;
        di = {40'd0, 6'd4, 6'd3, 6'd2, 6'd1};
        @(posedge clk);
        #1 rst = 1'b0;
        valid_i = 1'b1;
        @(posedge clk);
        #1 valid_i = 1'b0;
        wait (valid_o === 1'b1);
        #1;
        if (samples !== {23'd4, 23'd3, 23'd2, 23'd1})
            $fatal(1, "decoded samples failed");
        $display("PASS: tb_decoder");
        $finish;
    end
endmodule
