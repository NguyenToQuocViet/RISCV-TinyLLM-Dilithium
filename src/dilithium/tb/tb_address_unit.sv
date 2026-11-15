// Author: Nguyen Hung
// License: Nguyen Hung
`timescale 1ns/1ps
module tb_address_unit;
    logic clk = 1'b0;
    logic rst;
    logic [2:0] mode;
    logic [1:0] mode_resolver;
    logic en;
    logic [5:0] ram_nat, ram_addr;
    logic [7:0] twiddle_addr1, twiddle_addr2, twiddle_addr3, twiddle_addr4;
    logic ntt_round_done, done;

    address_unit dut (.*);
    always #5 clk = ~clk;

    initial begin
        rst = 1'b1;
        mode = 3'd3;
        mode_resolver = 2'd2;
        en = 1'b0;
        @(posedge clk);
        #1 rst = 1'b0;
        en = 1'b1;

        repeat (63) @(posedge clk);
        #1;
        if (done !== 1'b0 || ram_nat !== 6'd63 || ram_addr !== 6'd63)
            $fatal(1, "address sequence failed");
        @(posedge clk);
        #1;
        if (done !== 1'b1 || ntt_round_done !== 1'b0)
            $fatal(1, "operation completion failed");
        $display("PASS: tb_address_unit");
        $finish;
    end
endmodule
