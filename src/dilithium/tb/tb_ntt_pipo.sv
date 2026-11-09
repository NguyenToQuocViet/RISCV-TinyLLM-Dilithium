// Author: Luke Beckwith
// License: Apache-2.0
`timescale 1ns/1ps

module tb_ntt_pipo;
    logic clk = 1'b0;
    logic en;
    logic [95:0] datai, data0;

    NTT_PIPO #(.DEPTH(3)) dut (.*);
    always #5 clk = ~clk;

    initial begin
        en = 1'b1;
        datai = 96'h1;
        @(posedge clk); #1;
        datai = 96'h2;
        @(posedge clk); #1;
        datai = 96'h3;
        @(posedge clk); #1;
        if (data0 !== 96'h1) $fatal(1, "pipeline delay failed");
        datai = 96'h4;
        @(posedge clk); #1;
        if (data0 !== 96'h2) $fatal(1, "pipeline ordering failed");
        $display("PASS: tb_ntt_pipo");
        $finish;
    end
endmodule
