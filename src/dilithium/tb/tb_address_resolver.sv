// Author: Nguyen Hung
// License: Nguyen Hung
`timescale 1ns/1ps
module tb_address_resolver;
    logic [1:0] mapping;
    logic [5:0] addri, addro;

    address_resolver dut (.*);

    initial begin
        addri = 6'b101101; mapping = 0;
        #1;
        if (addro !== 6'b110110) $fatal(1, "decode map failed");
        mapping = 1;
        #1;
        if (addro !== 6'b011011) $fatal(1, "encode map failed");
        mapping = 2;
        #1;
        if (addro !== addri) $fatal(1, "standard map failed");
        $display("PASS: tb_address_resolver");
        $finish;
    end
endmodule
