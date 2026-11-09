// Author: Luke Beckwith
// License: Apache-2.0
`timescale 1ns/1ps

module tb_ntt_fifo;
    localparam logic [2:0] FORWARD_NTT_MODE = 3'd0;
    localparam logic [2:0] INVERSE_NTT_MODE = 3'd1;

    logic clk = 1'b0;
    logic rst, en;
    logic [2:0] mode;
    logic [95:0] data_in, new_value, data_out;

    ntt_fifo dut (.*);
    always #5 clk = ~clk;

    initial begin
        rst = 1'b1;
        en = 1'b0;
        mode = FORWARD_NTT_MODE;
        data_in = 96'h444444_333333_222222_111111;
        new_value = '0;
        @(posedge clk); #1;
        rst = 1'b0;
        en = 1'b1;

        @(posedge clk); #1;
        if (dut.piso_d.fifo[3] !== 24'h111111) $fatal(1, "PISO-D dispatch failed");
        @(posedge clk); #1;
        if (dut.piso_b.fifo[3] !== 24'h111111) $fatal(1, "PISO-B dispatch failed");
        @(posedge clk); #1;
        if (dut.piso_c.fifo[3] !== 24'h111111) $fatal(1, "PISO-C dispatch failed");
        @(posedge clk); #1;
        if (dut.piso_a.fifo[3] !== 24'h111111) $fatal(1, "PISO-A dispatch failed");

        mode = INVERSE_NTT_MODE;
        #1;
        if (data_out !== data_in) $fatal(1, "inverse read ordering failed");
        $display("PASS: tb_ntt_fifo");
        $finish;
    end
endmodule
