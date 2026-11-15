// Author: Nguyen Hung
// License: Nguyen Hung
`timescale 1ns/1ps
module tb_butterfly2x2;
    logic clk = 1'b0;
    logic rst;
    logic [2:0] mode;
    logic validi, valido;
    logic [95:0] datai, zetai, acci, datao;

    butterfly2x2 dut (.*);
    always #5 clk = ~clk;

    initial begin
        rst = 1'b1;
        mode = 3'd3;
        validi = 1'b0;
        datai = {24'd40, 24'd30, 24'd20, 24'd10};
        zetai = {24'd4, 24'd3, 24'd2, 24'd1};
        acci = '0;
        @(posedge clk);
        #1 rst = 1'b0;
        validi = 1'b1;
        wait (valido === 1'b1);
        #1;
        if (datao[23:0] !== 24'd13 || datao[47:24] !== 24'd21 ||
            datao[71:48] !== 24'd34 || datao[95:72] !== 24'd42)
            $fatal(1, "parallel addition paths failed");
        $display("PASS: tb_butterfly2x2");
        $finish;
    end
endmodule
