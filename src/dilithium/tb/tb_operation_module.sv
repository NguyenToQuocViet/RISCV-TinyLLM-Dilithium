// Author: Nguyen Hung
// License: Apache-2.0
`timescale 1ns/1ps

module tb_operation_module;
    localparam logic [2:0] ADD_MODE = 3'd3;
    logic clk = 1'b0;
    logic rst, start, done, web1, web2;
    logic [2:0] mode;
    logic [1:0] encode_mode;
    logic [5:0] addra1, addrb1, addra2, addrb2;
    logic [95:0] doa1, dob1, dib1, doa2, dib2;
    bit saw_write, saw_done;

    operation_module #(.ZETAS_INIT_FILE("")) dut (.*);
    always #5 clk = ~clk;

    initial begin
        rst = 1'b1; start = 1'b0; mode = ADD_MODE; encode_mode = '0;
        doa1 = '0; dob1 = '0; doa2 = '0;
        @(posedge clk); #1;
        rst = 1'b0;
        start = 1'b1;
        @(posedge clk); #1;
        start = 1'b0;
        for (int i = 0; i < 100; i++) begin
            @(posedge clk); #1;
            saw_write |= web2;
            saw_done |= done;
        end
        if (!saw_write || !saw_done) $fatal(1, "add operation did not complete its datapath transaction");
        $display("PASS: tb_operation_module");
        $finish;
    end
endmodule
