// Author: Nguyen Hung
// License: Apache-2.0
`timescale 1ns/1ps

module tb_keccak_cons;
    logic [4:0] addr;
    logic [63:0] rc_single;
    logic [127:0] rc_double;

    keccak_cons #(.UR(1)) dut_single (.addr, .rc(rc_single));
    keccak_cons #(.UR(2)) dut_double (.addr, .rc(rc_double));

    initial begin
        addr = 5'd0;
        #1;
        if (rc_single !== 64'h0000000000000001) $fatal(1, "round constant 0 failed");
        if (rc_double !== {64'h0000000000008082, 64'h0000000000000001})
            $fatal(1, "two-round constant ordering failed");
        addr = 5'd23;
        #1;
        if (rc_double !== {64'h0, 64'h8000000080008008})
            $fatal(1, "round constant wrap failed");
        $display("PASS: tb_keccak_cons");
        $finish;
    end
endmodule
