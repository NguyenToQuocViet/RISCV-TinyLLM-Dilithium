// Author: Nguyen Hung
// License: Nguyen Hung
`timescale 1ns/1ps
module tb_dual_port_rom;
    logic clk = 1'b0;
    logic en;
    logic [1:0] addra, addrb;
    logic [7:0] doa, dob;

    dual_port_rom #(.WIDTH(8), .LENGTH(4)) dut (.*);
    always #5 clk = ~clk;

    initial begin
        en = 1'b0;
        addra = 2'd1;
        addrb = 2'd3;
        dut.ram[1] = 8'hA5;
        dut.ram[3] = 8'h5A;
        #1 en = 1'b1;
        @(posedge clk);
        #1;
        if (doa !== 8'hA5 || dob !== 8'h5A)
            $fatal(1, "ROM read failed");
        $display("PASS: tb_dual_port_rom");
        $finish;
    end
endmodule
