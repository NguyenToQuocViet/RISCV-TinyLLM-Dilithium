// Author: Nguyen Hung
// License: Apache-2.0
`timescale 1ns/1ps

module tb_keccak_pkg;
    import keccak_pkg::*;

    logic [1599:0] state_string;
    state_table_t state_table;

    initial begin
        state_string = '0;
        state_string[1599 -: 320] = {320{1'b1}};
        state_table = str2table(state_string);
        if (get_keccak_capacity(256) != 1088) $fatal(1, "Keccak-256 capacity failed");
        if (get_keccak_capacity(512) != 576) $fatal(1, "Keccak-512 capacity failed");
        if (get_keccak_capacity(128) != 1344) $fatal(1, "SHAKE capacity failed");
        if (divceil(65, 64) != 2) $fatal(1, "divceil failed");
        if (state_table[0] !== {320{1'b1}} || state_table[4] !== '0)
            $fatal(1, "str2table lane mapping failed");
        $display("PASS: tb_keccak_pkg");
        $finish;
    end
endmodule
