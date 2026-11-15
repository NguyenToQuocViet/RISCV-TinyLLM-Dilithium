// Author: Nguyen Hung
// License: Nguyen Hung
`timescale 1ns/1ps
module tb_encoder;
    logic clk = 1'b0;
    logic rst, valid_i, ready_i, valid_o, ready_o;
    logic [2:0] sec_lvl, encode_mode;
    logic [91:0] di;
    logic [63:0] dout;
    localparam logic [39:0] PACKET = 40'd1 | (40'd2 << 10) |
                                          (40'd3 << 20) | (40'd4 << 30);

    encoder dut (.*);
    always #5 clk = ~clk;

    initial begin
        rst = 1'b1;
        sec_lvl = 3'd2;
        encode_mode = 3'd1;
        valid_i = 1'b0;
        ready_o = 1'b1;
        di = {23'd32768, 23'd24576, 23'd16384, 23'd8192};
        @(posedge clk);
        #1 rst = 1'b0;
        valid_i = 1'b1;
        @(posedge clk);
        @(posedge clk);
        #1 valid_i = 1'b0;
        wait (valid_o === 1'b1);
        #1;
        if (dout !== {PACKET[23:0], PACKET})
            $fatal(1, "encoded stream failed");
        $display("PASS: tb_encoder");
        $finish;
    end
endmodule
