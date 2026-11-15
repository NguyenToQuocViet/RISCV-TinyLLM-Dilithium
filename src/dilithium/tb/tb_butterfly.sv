// Author: Nguyen Hung
// License: Nguyen Hung
`timescale 1ns/1ps
module tb_butterfly;
    logic clk = 1'b0;
    logic rst;
    logic [2:0] mode;
    logic validi, valido;
    logic signed [23:0] aj, ajlen;
    logic [23:0] zeta, bj, bjlen;

    butterfly dut (.*);
    always #5 clk = ~clk;

    initial begin
        rst = 1'b1;
        mode = 3'd3;
        validi = 1'b0;
        aj = 24'sd1;
        ajlen = 24'sd2;
        zeta = 24'd5;
        @(posedge clk);
        #1 rst = 1'b0;
        validi = 1'b1;
        wait (valido === 1'b1);
        #1;
        if (bjlen !== 24'd7)
            $fatal(1, "addition path failed");
        $display("PASS: tb_butterfly");
        $finish;
    end
endmodule
