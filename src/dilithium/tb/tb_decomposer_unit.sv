// Author: Nguyen Hung
// License: Nguyen Hung
`timescale 1ns/1ps
module tb_decomposer_unit;
    logic clk = 1'b0;
    logic rst, valid_i, ready_i, valid_o, ready_o;
    logic [2:0] sec_lvl;
    logic [95:0] di, doa, dob;

    decomposer_unit dut (.*);
    always #5 clk = ~clk;

    initial begin
        rst = 1'b1;
        valid_i = 1'b0;
        ready_o = 1'b1;
        sec_lvl = 3'd2;
        di = {4{24'd95233}};
        @(posedge clk);
        #1 rst = 1'b0;
        valid_i = 1'b1;
        @(posedge clk);
        #1 valid_i = 1'b0;
        wait (valid_o === 1'b1);
        #1;
        if (dob !== {4{24'd1}} || doa !== {4{24'd8285186}})
            $fatal(1, "lane decomposition failed");
        $display("PASS: tb_decomposer_unit");
        $finish;
    end
endmodule
