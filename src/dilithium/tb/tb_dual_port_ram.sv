// Author: Nguyen Hung
// License: Nguyen Hung
`timescale 1ns/1ps
module tb_dual_port_ram;
    logic clk = 1'b0;
    logic ena, enb, wea, web;
    logic [1:0] addra, addrb;
    logic [7:0] dia, dib, doa, dob;

    dual_port_ram #(.WIDTH(8), .LENGTH(4)) dut (
        .clka(clk), .clkb(clk), .*
    );
    always #5 clk = ~clk;

    initial begin
        ena = 1; enb = 1; wea = 1; web = 1;
        addra = 1; addrb = 2; dia = 8'hA5; dib = 8'h5A;
        @(posedge clk); #1;
        if (doa !== 8'h00 || dob !== 8'h00) $fatal(1, "initial read failed");
        wea = 0; web = 0;
        @(posedge clk); #1;
        if (doa !== 8'hA5 || dob !== 8'h5A) $fatal(1, "readback failed");
        $display("PASS: tb_dual_port_ram");
        $finish;
    end
endmodule
