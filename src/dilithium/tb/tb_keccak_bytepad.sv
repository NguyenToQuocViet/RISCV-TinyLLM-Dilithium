// Author: Nguyen Hung
// License: Apache-2.0
`timescale 1ns/1ps

module tb_keccak_bytepad;
    logic [63:0] din_input, din_output, dout_input, dout_output;
    logic [7:0] sel_pad_location, sel_din, sel_dout;
    logic last_word, last_out_word;
    logic [1:0] mode;

    keccak_bytepad dut (.*);

    initial begin
        din_input = 64'h8877665544332211;
        dout_input = 64'h1020304050607080;
        sel_pad_location = 8'b00000001;
        sel_din = 8'b00000010;
        sel_dout = 8'b00000101;
        last_word = 1'b0;
        last_out_word = 1'b0;
        mode = 2'b10;
        #1;
        if (din_output[7:0] !== 8'h1f || din_output[15:8] !== 8'h22)
            $fatal(1, "SHAKE byte padding failed");
        if (dout_output !== dout_input) $fatal(1, "ordinary output forwarding failed");
        last_word = 1'b1;
        last_out_word = 1'b1;
        #1;
        if (din_output[7:0] !== 8'h9f) $fatal(1, "last SHAKE padding byte failed");
        if (dout_output !== 64'h0000000000600080) $fatal(1, "last output masking failed");
        $display("PASS: tb_keccak_bytepad");
        $finish;
    end
endmodule
