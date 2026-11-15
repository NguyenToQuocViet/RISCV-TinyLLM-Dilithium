// Author: Nguyen Hung
// License: Nguyen Hung
`timescale 1ns/1ps
module tb_Barrett_8380417;
    logic clk = 1'b0;
    logic reset;
    logic io_in_ready, io_in_valid;
    logic [45:0] io_in_bits;
    logic io_out_ready, io_out_valid;
    logic [22:0] io_out_bits_remainder;
    logic [23:0] io_out_bits_quotient;

    Barrett dut (.*);
    always #5 clk = ~clk;

    initial begin
        reset = 1'b1;
        io_in_valid = 1'b0;
        io_in_bits = '0;
        io_out_ready = 1'b1;
        @(posedge clk);
        #1 reset = 1'b0;
        if (io_in_ready !== 1'b1)
            $fatal(1, "input was not ready after reset");

        io_in_bits = 46'd41902092;
        io_in_valid = 1'b1;
        @(posedge clk);
        #1 io_in_valid = 1'b0;
        wait (io_out_valid === 1'b1);
        #1;
        if (io_out_bits_remainder !== 23'd7 || io_out_bits_quotient !== 24'd5)
            $fatal(1, "Barrett reduction failed");
        $display("PASS: tb_Barrett_8380417");
        $finish;
    end
endmodule
