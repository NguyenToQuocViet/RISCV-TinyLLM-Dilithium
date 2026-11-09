// Author: Luke Beckwith
// License: Apache-2.0
`timescale 1ns/1ps

module tb_twiddle_resolver;
    localparam logic [2:0] FORWARD_NTT_MODE = 3'd0;
    localparam logic [2:0] INVERSE_NTT_MODE = 3'd1;

    logic clk = 1'b0;
    logic rst, en;
    logic [2:0] mode;
    logic [5:0] k;
    logic [3:0] s;
    logic [7:0] twiddle_addr1, twiddle_addr2, twiddle_addr3, twiddle_addr4;

    twiddle_resolver dut (.*);
    always #5 clk = ~clk;

    initial begin
        mode = FORWARD_NTT_MODE;
        k = '0;
        s = '0;
        rst = 1'b1;
        en = 1'b0;
        @(posedge clk); #1;
        if ({twiddle_addr1, twiddle_addr2, twiddle_addr3, twiddle_addr4} !==
            {8'd1, 8'd1, 8'd2, 8'd3})
            $fatal(1, "forward twiddle initialization failed");

        mode = INVERSE_NTT_MODE;
        s = 4'd1;
        k = '0;
        @(posedge clk); #1;
        rst = 1'b0;
        if ({twiddle_addr1, twiddle_addr2, twiddle_addr3, twiddle_addr4} !==
            {8'd127, 8'd126, 8'd63, 8'd63})
            $fatal(1, "inverse twiddle initialization failed");
        $display("PASS: tb_twiddle_resolver");
        $finish;
    end
endmodule
