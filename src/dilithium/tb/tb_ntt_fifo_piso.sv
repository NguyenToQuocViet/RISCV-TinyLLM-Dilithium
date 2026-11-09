// Author: Luke Beckwith
// License: Apache-2.0
`timescale 1ns/1ps

module tb_ntt_fifo_piso;
    logic clk = 1'b0;
    logic en, piso_en;
    logic [95:0] line;
    logic [23:0] new_value, data_out;
    logic [95:0] fifo_out;

    ntt_fifo_piso #(.DEPTH(4)) dut (.*);
    always #5 clk = ~clk;

    initial begin
        en = 1'b1;
        piso_en = 1'b1;
        line = 96'h444444_333333_222222_111111;
        new_value = '0;
        @(posedge clk); #1;
        if (fifo_out !== line || data_out !== '0)
            $fatal(1, "parallel load failed");

        piso_en = 1'b0;
        new_value = 24'hAAAAAA;
        @(posedge clk); #1;
        if (fifo_out !== 96'hAAAAAA_444444_333333_222222 || data_out !== 24'h111111)
            $fatal(1, "shift failed");
        $display("PASS: tb_ntt_fifo_piso");
        $finish;
    end
endmodule
